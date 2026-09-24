"""The disposition ledger: how `H subset-of R` is made structurally true (AD A.7a).

The inversion this module exists for:

    withheld := H - disclosed          # a set difference computed at envelope time,
                                       # NOT populated by the rung or cap that dropped the ID
    H == disclosed union withheld      # checked before the response leaves the process

Under the old shape, `withheld` was right only if every future cap remembered to write to
it. Here the *set* is derived from `H`, so a cap that forgets cannot shrink it; what a cap
still owes is the *reason*, and a residue with no reason is an error - loudly - rather
than a silent loss.

Three residues are errors, not two, because the inverse bug is just as bad:

  * an ID in `H - disclosed` with no cap note  -> a cap dropped a hit and said nothing;
  * a cap note for an ID that IS disclosed     -> a cap claimed to withhold something present
                                                  (depth reduction is not omission, A.7a);
  * a cap note for an ID that is not in `H`    -> a rung fetched IDs without recording them,
                                                  i.e. `H` is under-counted and the invariant
                                                  would pass vacuously.

The same inversion, one layer earlier (R-ORCH-001 / R-ARCH-005): `H` used to be whatever a
caller chose to hand `record_list_page`, so a rung that fetched 100 IDs and recorded 10
satisfied every check above with 90 messages invisible. `H` is now accumulated from
`FetchedIds` - a sealed page object a transport produces at the moment of the call and
which carries no public way to read the IDs back out. A caller cannot hold a bare ID list
long enough to shrink it: the only readable enumeration is `ledger.hit_ids`, which is `H`
itself. See `mailweave.retrieval.transport` for the calling side.

And the same inversion once more, at the last intake that was still asserting
(R-RETR round 2, H1b): `record_shortlist` used to take a bare `Iterable[str]` and put
every element into `H` under clause H-sem. R-RETR injected 37 IDs no retrieval ever
returned, filed self-issued withheld notes for them, and rebuilt R-DISC-001's dishonest
5-of-42 map as a valid envelope. The seal is structural rather than a new check bolted
onto certification:

  * `_admit` is the **only** writer of `self._origins`, and it takes a `FetchedIds`. There
    is now no code path anywhere in this class by which an ID enters `H` without having
    been released from a sealed page. `record_shortlist` does not call it;
  * a shortlist is therefore a **selection out of `H`**, not an intake into it, and IDs of
    unknown provenance are refused at intake rather than at certification;
  * `Shortlist.size` is derived from the deduplicated selection, so the reported size is
    what was enumerated rather than what the caller said alongside it.

**What that narrows, stated rather than glossed.** AD A.7a defines `H` as the union of
three clauses, of which H-sem is "the shortlist that enters the disclosure candidate set".
Under this seal H-sem is a *subset* of the observed clauses rather than an independent
third source. That is a real narrowing of the written definition and it is deliberate:
what it forbids is the case A.7a never contemplated and R-RETR exploited - a scored
retriever shortlisting an ID that no executed retrieval ever returned.

**Amendment A2 (round 4): the observed clauses are not two.** Round 3 wrote the seal with
exactly `messages.list` and `history.list` in it, because those were the only endpoints
any rung had reached at the time. R-RETR-004 showed that encoded an implementation detail
as if it were the principle: AD D.5 builds the semantic candidate pool *thread-wise*, and
its first-priority source arrives through `threads.get`. A legitimate top-k selection from
that pool would have been refused by the seal, and the pressure that puts on the next
implementer is to reopen `record_shortlist` - which is how H1 came to be open the first
time.

The principle is that **an ID may only enter `H` by having been observed in a real Gmail
response**. So a sealed page generalises to a sealed *observation* which carries the
endpoint that produced it (`ObservedEndpoint`), the clause is derived from that endpoint
rather than asserted by whoever records it, and `threads.get` is a first-class clause
(H-thr) beside H-lex and H-hist. Nothing about the seal loosens:

  * `_admit` is still the only writer of `self._origins`, and still takes a sealed
    observation - there is still no path by which a bare ID list enters `H`;
  * an observation is admitted only through the intake that matches its endpoint, so a
    `threads.get` response cannot be recorded as a `messages.list` page and have a
    scan-scope entry invented for a query that never ran;
  * adding an observed source is the opposite of accepting an unsourced one. A1 still
    applies: none of this is a guarantee until a witness outside the process exists.

**And once more, at the last claim that was still asserted (R-DISC-009).** A withheld
record says *which thread* is missing a message, and round 5 took that thread as an
argument to `note_withheld`. Membership of `withheld` was derived, the reason was
supplied, and the identity was neither - so a map of thread A could close its own
arithmetic by naming a real withheld id belonging to thread B, and every check downstream
agreed with it because they all compared the record against the caller's own value. It is
not adversarial-only: the wrong `thread_id` inside a loop over threads does it silently.

The thread is now read off the observation that returned the id (`HitOrigin.thread_id`,
written by `_admit` and now also *read*), and `note_withheld` has no `thread_id` parameter
to get wrong. A sealed observation therefore has to carry what Gmail already tells it:
`threads.get` names its one thread, and the two listing endpoints carry `threadId` on
every item, which `FetchedIds(thread_ids=...)` records. An id observed with no thread can
be a hit and can be disclosed; it cannot be *withheld*, because there is no honest way to
say which thread is short of a message.

**And once more, on the other side of the same fence (R-DISC-011, round 7).** Deriving the
*withheld* record's thread left the *disclosed* rows asserting theirs. A `map_id`-bearing
source for thread A could reach `accounted_for == stated_total` by carrying a row for a
real message a real `threads.get` had observed in thread B, with `partial=False`, because
every check in the payload compared the row against the source's own claim and nothing
outside this module could read `HitOrigin`. So the certificate now carries
`observed_threads` - the thread each id in `H` was observed under - and `Envelope` holds
every disclosed id to it, refusing a source that shows a message the ledger saw elsewhere
and refusing a *map* that counts an id no observation placed in its thread. The same
enumeration also bounds `stated_total` from below: a thread cannot hold fewer messages than
the number of its own messages that were actually seen.

**What that does not close, because field-level derivation cannot.** The seal records a
*subset* of what a Gmail response says. `stated_total`, a row's `position`, `internal_date`
and `history_id` are all facts of a real response that no `FetchedIds` carries, so they have
no observed value to be derived from and remain caller-owned by default rather than by
argument - see the round 7 audit in `docs/reviews/ROUND_07/HANDOFF.md`. Closing the class
needs the observation to record the whole response it saw, and then A1's content witness to
bound the observation itself.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, NamedTuple

from mailweave.constants import (
    GMAIL_NUMERIC_ID_RE,
    MAX_GMAIL_NUMERIC_ID_DIGITS,
    is_one_line,
)
from mailweave.envelope.grouping import GroupKey, arrange_groups
from mailweave.envelope.reasons import RungId
from mailweave.envelope.vocab import WithheldCap, WithheldGranularity
from mailweave.envelope.wire import (
    Affordance,
    ScanScopeEntry,
    Shortlist,
    WithheldGroup,
    WithheldRecord,
    WithheldTail,
    parse_instant,
)
from mailweave.errors import DispositionInvariantError
from mailweave.sealing import IdentityRegistry


class ObservedEndpoint(StrEnum):
    """A Gmail endpoint whose response may put an ID into `H` (AD A.7a, amendment A2).

    The value an id enters `H` under is decided by *which call was executed*, not by which
    ledger method a caller reached for, which is why this travels on the observation rather
    than being passed alongside it. Adding a member here is adding a clause to A.7a and is
    an architecture amendment, not a refactor: `CLAUSE_BY_ENDPOINT` below has to name it,
    and `DispositionLedger` has to grow the intake that admits it.
    """

    MESSAGES_LIST = "messages.list"
    HISTORY_LIST = "history.list"
    THREADS_GET = "threads.get"


CLAUSE_BY_ENDPOINT: Final[Mapping[ObservedEndpoint, str]] = MappingProxyType(
    {
        ObservedEndpoint.MESSAGES_LIST: "H-lex",
        ObservedEndpoint.HISTORY_LIST: "H-hist",
        ObservedEndpoint.THREADS_GET: "H-thr",
    }
)
"""A.7a's clause for each observed endpoint. H-thr is amendment A2's addition."""


_RECORD_TOKEN = object()
"""Private capability token. Only `DispositionLedger` holds it.

It is what makes `FetchedIds` openable by the ledger and by nothing else. Like
`_MINT_TOKEN` below, it is not a defence against code that deliberately reaches for a
private attribute in the same process, and is not claimed to be. What it removes is the
*ordinary* way to under-record: there is no supported call that hands a caller the IDs a
page returned.
"""


#: The longest a **string** field of a sealed observation may be, and the reason amendment
#: A6 could be applied at all (round 8).
#:
#: A6 widens the seal to carry the named scalars the class-O audit found - `stated_total`,
#: `position`, `internal_date`, `history_id`, `fetched_at` - and **not** whole response
#: bodies. Mail text is excluded, and it is excluded *by shape* rather than by intention:
#: every field A6 adds is either an `int` or a single-line string of at most this many
#: characters. A subject does not fit reliably; a body does not fit at all; and a value
#: carrying a newline is refused outright. That is what makes "this does not become a place
#: bodies quietly persist" (OD-4, `SCOPE_CORRECTION.md` A.3) a checkable statement rather
#: than a promise - see `test_no_widened_seal_field_can_hold_mail_text`.
#:
#: 64 is chosen against the values themselves, not tuned: Gmail's `internalDate` is 13
#: digits, a `historyId` is at most 20, and an RFC 3339 instant with an offset is 25.
MAX_SEALED_SCALAR_CHARS: Final = 64


#: R-SEC-029's predicate, under its round-9 name. **The implementation moved to
#: `mailweave.constants` in round 11** and this is now the one import, not a second copy:
#: `reasons.py` had independently reimplemented it (R-ARCH-031, the sixth appearance of "one
#: shape validated, peers trusted"), and the preflight record writer in the harness package
#: needed it a third time, where nothing under `envelope/` is reachable at all. Three layers,
#: one predicate, maintained in the module all three already import for `GMAIL_NUMERIC_ID_RE`.
_is_one_line = is_one_line


#: The shape check itself now lives in `mailweave.constants`, imported above and re-exported
#: under its round-9 private name so this module reads unchanged. It moved because round 10
#: found the *same field name* unchecked one layer up, in `envelope/reasons.py`, where a
#: whole English sentence reached the disclosed JSON wire (R-SEC-032). Two layers checking
#: one Gmail shape must not hold two independently written copies of it: the second copy is
#: what nobody wrote. **ASCII** digits, deliberately - `"١٣".isdigit()` and `"²".isdigit()`
#: are both `True` and neither is anything Gmail emits (R-SEC-030).
_GMAIL_NUMERIC_ID_RE = GMAIL_NUMERIC_ID_RE


def _sealed_scalar(field: str, value: str) -> str:
    """Refuse a string that could carry mail text into the seal (amendment A6).

    Three conditions, all mechanical: non-empty, at most `MAX_SEALED_SCALAR_CHARS`, and a
    **single line** by `str.splitlines()`' definition. The last one is what stops the
    interesting attempt - a 64-character prefix of a body is still mail text, but a body
    pasted whole is not, and the length bound alone would let a caller store one short line
    per id.

    It is the floor rather than the whole check. A field with a *known shape* gets that shape
    checked as well - see `_sealed_numeric_id` and `parse_instant` - because "64 characters
    on one line" admits an entire English sentence, which is exactly what R-SEC-030 put on
    the wire under a metadata field name.
    """
    if not value:
        raise DispositionInvariantError(
            f"{field} on a sealed observation is empty; omit it rather than sealing a "
            "value that states nothing"
        )
    if len(value) > MAX_SEALED_SCALAR_CHARS:
        raise DispositionInvariantError(
            f"{field} is {len(value)} characters, over the {MAX_SEALED_SCALAR_CHARS}-character "
            "bound a sealed scalar carries. Amendment A6 widens the seal to named scalars "
            "and explicitly not to response bodies: mail text is excluded from what a seal "
            "retains, and the bound is how that exclusion is enforced rather than promised "
            "(OD-4, SCOPE_CORRECTION A.3)"
        )
    if not _is_one_line(value):
        raise DispositionInvariantError(
            f"{field} carries a line break. A sealed scalar is one field of one Gmail "
            "response - a count, an index, an id, an instant - and a multi-line value is "
            "content, which amendment A6 excludes from the seal (OD-4). Every boundary "
            "`str.splitlines()` recognises counts, not only \\n and \\r (R-SEC-029)"
        )
    return value


def _sealed_numeric_id(field: str, value: str) -> str:
    """A sealed scalar that must also be the decimal number Gmail actually returns.

    R-SEC-030. `fetched_at` was checked against a real shape by `parse_instant`; `history_id`
    and `internal_date` were checked against a length and a character class, so any
    64-character single-line string was accepted - and a reviewer put

        "Please review the attached NDA before end of day."

    on the JSON wire under both field names, **including on a stub row**, whose entire
    architectural purpose is to disclose nothing. One field validated and its two peers
    trusted is the fourth appearance of that pattern in this project, which is why the fix is
    to give the peers the same treatment rather than to widen the length bound.

    **Why a stub row keeps its `internal_date` at all**, stated rather than left to be
    rediscovered: with this check the field can only be a decimal timestamp, which is the
    same class of bookkeeping scalar as the `position` a stub row already carries and which
    orders it inside its thread. Contract R-04's stub tier withholds *content*, and a
    millisecond count is not content. What made the reviewer's finding real was that the
    field was not checked, not that stubs carry a date - so the check is the fix, and this
    paragraph is the "or document explicitly why" half of the required fix, on the record.
    """
    _sealed_scalar(field, value)
    if _GMAIL_NUMERIC_ID_RE.match(value) is None:
        raise DispositionInvariantError(
            f"{field}={value!r} is not the shape Gmail returns. A `historyId` is an unsigned "
            "64-bit integer and an `internalDate` is milliseconds since the epoch, both "
            "rendered as at most "
            f"{MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal digits. A metadata field that "
            "accepts prose is a place mail text reaches the wire under a name that says it "
            "is not mail text (R-SEC-030, OD-4)"
        )
    return value


#: The longest a Gmail message or thread id is in practice: they are short hex-ish strings,
#: and the seal has always held them (amendment A2, round 4). R-SEC-031 found them carrying
#: **no** bound at all - not a length, not a line-break refusal - while round 8's reflection
#: test exempted them and claimed to prove "a future field of the wrong shape fails here".
#: They are bounded now, so the claim and the coverage are the same statement.
MAX_SEALED_ID_CHARS: Final = MAX_SEALED_SCALAR_CHARS


#: A Gmail continuation token is opaque and has **no documented shape**, so unlike every
#: other string the seal retains it cannot be checked against one. **[PREFLIGHT PF-18]**: the
#: real length is measured on the first live run rather than guessed again, and a token over
#: this bound stops pagination entirely, so the question is registered in AD §F rather than
#: left in this comment. What it gets is the floor
#: - non-empty, single-line, bounded - at a width that will not refuse a real token. Stated
#: rather than glossed: 256 single-line characters is a place a sentence fits, so this field
#: is *narrowed* and not closed, and it is the weakest string bound in the seal. It is here
#: because round 8's reflection test skipped it entirely (its fixture is a `threads.get`,
#: which has no page token) while claiming every retained value was bounded - the same shape
#: as R-SEC-031, one field wider, found by this round's own sweep.
MAX_SEALED_PAGE_TOKEN_CHARS: Final = 256


def _sealed_page_token(field: str, value: str) -> str:
    """The floor, for the one sealed string with no shape to check against."""
    if not value:
        raise DispositionInvariantError(
            f"{field} on a sealed observation is empty; omit it rather than sealing a "
            "value that states nothing"
        )
    if len(value) > MAX_SEALED_PAGE_TOKEN_CHARS or not _is_one_line(value):
        raise DispositionInvariantError(
            f"{field} is {len(value)} characters and "
            f"{'one line' if _is_one_line(value) else 'multi-line'}; a Gmail continuation "
            f"token is a short single-line string and the seal bounds it at "
            f"{MAX_SEALED_PAGE_TOKEN_CHARS} characters. It is the one sealed string with no "
            "documented shape, so this bound is a floor and not a proof (OD-4)"
        )
    return value


def _sealed_id(field: str, value: str) -> str:
    """An id the seal retains, bounded like every other string it retains (R-SEC-031).

    Deliberately *not* given a character-class check. A Gmail message id is hex, but this
    repository's own fixtures and every reviewer's probe use ids like `"m1"` and `"ghost-1"`,
    and a shape check here would refuse the tests that attack the ledger rather than any
    attack. What R-SEC-031 found is the absence of any bound, and a bound is what it gets:
    non-empty, at most `MAX_SEALED_ID_CHARS`, one line. Five lines of mail text no longer
    fit, which was the reproduction.
    """
    if not value:
        raise DispositionInvariantError(
            f"{field} on a sealed observation is empty; an observation cannot record an id "
            "the response did not name"
        )
    if len(value) > MAX_SEALED_ID_CHARS or not _is_one_line(value):
        raise DispositionInvariantError(
            f"{field} is {len(value)} characters and "
            f"{'one line' if _is_one_line(value) else 'multi-line'}; a Gmail id is a short "
            f"single-line string and the seal bounds every string it retains at "
            f"{MAX_SEALED_ID_CHARS} characters. R-SEC-031: the id fields carried no bound "
            "at all while the round-8 reflection test exempted them and claimed broader "
            "protection than it had"
        )
    return value


class FetchedIds:
    """The message IDs one executed Gmail call returned, sealed until recorded.

    A *sealed observation* (amendment A2). This is the object a Gmail wrapper constructs at
    the moment of the HTTP call, and it is the only accepted input to the ledger's `H`
    accumulation. It carries the `endpoint` that produced it, because that is what decides
    which A.7a clause its ids enter under - `messages.list` -> H-lex, `history.list` ->
    H-hist, `threads.get` -> H-thr - and that decision belongs to the call that was really
    executed rather than to whichever ledger method a caller later reaches for.

    It deliberately has:

      * no `ids` property, no `__iter__`, no `__getitem__` - the IDs are not readable
        through any public member;
      * `size`, `more_pages` and `next_page_token`, which are what a paginating caller
        actually needs and none of which is a message ID;
      * a one-shot `_release` that only `DispositionLedger` can call.

    The pagination fields are meaningful for a listing endpoint and absent for the others:
    a `threads.get` response is one thread, not a page of a result set, so inventing a
    `page_size` for it would put a number in `scan_scope` that no call ever had. The
    constructor requires each endpoint to carry what that endpoint really has.

    The thread each id belongs to is one of those things (R-DISC-009). A `threads.get`
    carries the one `thread_id` all its rows share; `messages.list` and `history.list`
    carry a `threadId` per item, which is what `thread_ids` records. It is optional only
    because no Gmail client exists yet to supply it - what it costs to omit is stated
    where it bites: an id observed with no thread cannot be named in a withheld record,
    because `certify` derives that record's thread from here and will not invent one.

    So the shape of R-ORCH-001's probe - fetch 100, record 10 - has nowhere to stand: the
    100 are inside the ledger before the transport call returns, and the caller never
    holds a list it could truncate.

    **What this seal is not, stated here rather than discovered later.** It bounds
    *under*-recording, in the direction R-ORCH-001 attacked. It does not bound
    *over*-recording: `FetchedIds(ids=[...], endpoint=..., page_size=50)` is an ordinary
    public constructor, so any in-process code can mint an observation of ids nothing
    fetched - under any endpoint it likes, A2 changes nothing here either - and hand it
    to `record_list_page`. That is the same fabrication R-RETR performed through
    `record_shortlist`, one call to the left, and H1b does not close it - see
    `tests/test_disposition_invariant.py::test_a_hand_built_page_is_accepted_and_that_is_the_documented_residual`.

    The same is true of the thread map R-DISC-009 added: an observation that can claim ids
    nothing fetched can claim threads nothing observed, so deriving the record's thread from
    the observation removes the *caller's* unchecked assertion, not every unchecked
    assertion. What it buys is that the claim now has to be made at the moment of the call,
    by the code that says it executed it, in the same object the ids came out of - and the
    content witness A1 requires would check it against the real response, exactly as it
    checks the ids.

    It is not closed here because within one process it is not closeable. The page's
    provenance is the assertion "I executed this call", and the only code that can make it
    is the Gmail wrapper that really does execute it - so any constructor reachable by the
    real wrapper is reachable by a fake one, and moving the constructor behind a
    capability token would change who must reach for a private name without changing what
    is possible. Making the claim checkable needs a witness outside the process: the
    counting proxy `IMPLEMENTATION_PLAN.md` already assigns to WS-13 - and per amendment
    A1 it has to be a *content* witness recording the id set of every observed response,
    not the call counter WS-13's acceptance line currently describes, because a count
    cross-check cannot tell one real call returning five ids from one real call whose
    thirty-two extra ids were minted here. Until that exists, `|H|` is bounded below by
    what the transport fetched and bounded above by nothing.

    **Subclassing is refused, and buys less here than it does next door.** Amendment A1 named
    the move in terms - "even a capability token is defeated by subclassing and overriding
    `_release`" - and it stayed possible for ten rounds. Closing it stops the one-shot latch
    being overridden. It does **not** touch the over-recording residue above: the constructor
    is public by design, so an in-process caller who wants to fabricate an observation never
    needed a subclass. Round 13 closed it for uniformity with the other two capability
    objects, so the standing sweep needs no exception list, not because it changes what A1
    says is unclosable.

    **What it does not do to `retrieval/transport.py`'s `isinstance(page, FetchedIds)`
    checks.** Round 13 said closing subclassing made those "mean the class rather than
    anything shaped like it". It does not: a plain object with a `__class__` property returning
    this class passes `isinstance` without being a subclass, which is R-SEC-054 one module
    over, and it is executed against this class in
    `tests/test_reader_seal_round14.py::test_an_isinstance_check_is_not_a_type_check_for_this_class_either`.
    Those two checks are guards against a *fetcher returning the wrong thing* - a mistake,
    loudly - and not against forgery. What the ledger rests on is `_release`, which a duck may
    of course implement; that is the same residue as the public constructor, bounded by A1's
    unbuilt content witness and by nothing here.
    """

    __slots__ = (
        "__weakref__",
        "_consumed",
        "_endpoint",
        "_fetched_at",
        "_history_id",
        "_ids",
        "_internal_dates",
        "_more_pages",
        "_next_page_token",
        "_page_size",
        "_positions",
        "_stated_total",
        "_thread_id",
        "_thread_ids",
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            "FetchedIds may not be subclassed: a subclass replaces the one-shot `_release` "
            "and hands the ledger ids the observation it claims to be never carried, without "
            "presenting the record token at all - which is the move amendment A1 named and "
            "which the token cannot refuse. It does not make the seal complete: the "
            "constructor is public, and `|H|` stays bounded above by nothing until A1's "
            "content witness exists"
        )

    def __init__(
        self,
        *,
        ids: Iterable[str],
        endpoint: ObservedEndpoint,
        page_size: int | None = None,
        more_pages: bool = False,
        next_page_token: str | None = None,
        thread_id: str | None = None,
        thread_ids: Mapping[str, str] | None = None,
        stated_total: int | None = None,
        positions: Mapping[str, int] | None = None,
        internal_dates: Mapping[str, str] | None = None,
        history_id: str | None = None,
        fetched_at: str | None = None,
    ) -> None:
        if endpoint is ObservedEndpoint.MESSAGES_LIST and (page_size is None or page_size <= 0):
            raise DispositionInvariantError(
                "a messages.list observation must carry the page size the call was made "
                "with; scan_scope reports it, and a page whose size is unknown cannot be "
                "reported honestly (AD A.7a, GMAIL-04)"
            )
        if endpoint is ObservedEndpoint.THREADS_GET and not thread_id:
            raise DispositionInvariantError(
                "a threads.get observation must name the thread it observed; without it "
                "the ids it admits under H-thr cannot be joined back to the call that "
                "returned them (amendment A2)"
            )
        if endpoint is ObservedEndpoint.THREADS_GET and thread_ids is not None:
            raise DispositionInvariantError(
                "a threads.get observation already names the one thread every row it "
                "returned belongs to; a second per-id map beside it would be a divergent "
                "statement of the same observed fact (R-DISC-009)"
            )
        self._ids: tuple[str, ...] = tuple(_sealed_id("id", value) for value in ids)
        self._endpoint = endpoint
        self._page_size = page_size
        self._more_pages = more_pages
        self._next_page_token = (
            _sealed_page_token("next_page_token", next_page_token)
            if next_page_token
            else next_page_token
        )
        self._thread_id = _sealed_id("thread_id", thread_id) if thread_id else thread_id
        self._thread_ids: Mapping[str, str] = MappingProxyType(
            {
                message_id: _sealed_id("thread_ids", value)
                for message_id, value in (thread_ids or {}).items()
            }
        )
        if thread_ids is not None:
            unknown = sorted(set(self._thread_ids) - set(self._ids))
            if unknown:
                raise DispositionInvariantError(
                    f"this {endpoint.value} observation names a thread for ids it did not "
                    f"return: {unknown}. Which thread an id belongs to is a fact of the "
                    "response that returned it, and cannot be recorded for an id that "
                    "response never carried (R-DISC-009)"
                )
            missing = sorted(set(self._ids) - set(self._thread_ids))
            if missing:
                raise DispositionInvariantError(
                    f"this {endpoint.value} observation names a thread for some of its ids "
                    f"and not for {missing}. Gmail carries `threadId` on every item of a "
                    "messages.list page and on every messagesAdded entry, so a partial map "
                    "is an account of the response missing part of what it said (R-DISC-009)"
                )

        # -- amendment A6: the named scalars the class-O audit found -------------------
        #
        # Each of these is a fact the Gmail response stated and the round 7 seal threw
        # away, which is why `Source.stated_total`, `MessageRow.position`,
        # `MessageRow.internal_date`, `Source.history_id` and `Source.fetched_at` had
        # nothing to derive from and "derive it" degenerated into checking one caller
        # assertion against another. They are optional for the same reason `thread_ids` is:
        # no Gmail client exists yet to supply them. What it costs to omit one is stated
        # where it bites - an envelope field with no observed value behind it keeps the
        # weaker check it had, and the response says nothing it could not check.
        self._stated_total = stated_total
        self._history_id = _sealed_numeric_id("history_id", history_id) if history_id else None
        self._fetched_at = _sealed_scalar("fetched_at", fetched_at) if fetched_at else None
        if self._fetched_at is not None:
            parse_instant("fetched_at", self._fetched_at)
        if stated_total is not None:
            if endpoint is not ObservedEndpoint.THREADS_GET:
                raise DispositionInvariantError(
                    f"a {endpoint.value} observation cannot state a thread's message "
                    "count: a listing page is a page of a result set, not a thread, and "
                    "`stated_total` is the thread's own length (amendment A6, A3)"
                )
            if stated_total < len(self._ids):
                raise DispositionInvariantError(
                    f"this observation returned {len(self._ids)} messages and states the "
                    f"thread holds {stated_total}. A thread cannot be shorter than the "
                    "number of its messages one response returned (amendment A3, A6)"
                )
        self._positions: Mapping[str, int] = MappingProxyType(dict(positions or {}))
        if positions is not None:
            if endpoint is not ObservedEndpoint.THREADS_GET:
                raise DispositionInvariantError(
                    f"a {endpoint.value} observation cannot state a message's position in "
                    "its thread: a position is an index into one thread's chronological "
                    "order, and only threads.get returns that order (amendment A6, A3)"
                )
            self._require_a_total_map("positions", self._positions)
            for message_id, position in self._positions.items():
                if position < 0:
                    raise DispositionInvariantError(
                        f"position {position} observed for {message_id!r} is negative; a "
                        "position is a 0-based index into chronological order (A3)"
                    )
                if stated_total is not None and position >= stated_total:
                    raise DispositionInvariantError(
                        f"position {position} observed for {message_id!r} is outside a "
                        f"thread of {stated_total} messages (amendment A3: 0 <= p < "
                        "stated_total)"
                    )
            occupied = sorted(self._positions.values())
            if len(set(occupied)) != len(occupied):
                raise DispositionInvariantError(
                    "this observation puts two of its messages at the same position in "
                    "the thread; a position holds one message (A.7a, A3)"
                )
        self._internal_dates: Mapping[str, str] = MappingProxyType(
            {
                message_id: _sealed_numeric_id("internal_date", value)
                for message_id, value in (internal_dates or {}).items()
            }
        )
        if internal_dates is not None:
            self._require_a_total_map("internal_dates", self._internal_dates)
        self._consumed = False

    def _require_a_total_map(self, field: str, supplied: Mapping[str, object]) -> None:
        """A per-id map must name every id this observation returned, and no other.

        The same rule `thread_ids` has followed since R-DISC-009, and for the same reason:
        a partial map is an account of the response missing part of what it said, and a map
        naming an id the response never carried is a statement about something this
        observation did not observe.
        """
        unknown = sorted(set(supplied) - set(self._ids))
        if unknown:
            raise DispositionInvariantError(
                f"this {self._endpoint.value} observation states {field} for ids it did "
                f"not return: {unknown}. A sealed scalar is a fact of the response that "
                "returned the id, and cannot be recorded for an id that response never "
                "carried (amendment A6, R-DISC-009)"
            )
        missing = sorted(set(self._ids) - set(supplied))
        if missing:
            raise DispositionInvariantError(
                f"this {self._endpoint.value} observation states {field} for some of its "
                f"ids and not for {missing}. Gmail carries this field on every message of "
                "the response, so a partial map is an account of the response missing part "
                "of what it said (amendment A6, R-DISC-009)"
            )

    @property
    def size(self) -> int:
        """How many IDs this observation carried. A count is not an ID."""
        return len(self._ids)

    @property
    def endpoint(self) -> ObservedEndpoint:
        """Which Gmail call produced this observation, and so which clause it enters."""
        return self._endpoint

    @property
    def thread_id(self) -> str | None:
        """The thread a `threads.get` observed. A thread id is not a message id."""
        return self._thread_id

    def _thread_of(self, message_id: str) -> str | None:
        """The thread *this response* said `message_id` belongs to, or `None` (R-DISC-009).

        One thread for every row of a `threads.get`; the per-id `threadId` Gmail carries on
        each item for the two listing endpoints. It is a read of the observation, not a
        value a caller may state beside it, which is the whole of R-DISC-009's fix: the
        thread a withheld record is charged against is derived from here.

        `None` means this observation did not record a thread for that id, and a withheld
        record for it therefore cannot be filed - not that the id has no thread.

        Private, like `_release` and for the same reason: answering "which thread is id X
        in" for an arbitrary string is a membership oracle over the sealed page, which is
        one step from the enumeration the seal exists to withhold. The ledger is the only
        caller, and `test_a_fetched_page_has_no_public_member_that_yields_an_id` is what
        holds that line.
        """
        if self._thread_id is not None:
            return self._thread_id
        return self._thread_ids.get(message_id)

    def _scalars_of(self, message_id: str) -> tuple[int | None, str | None]:
        """The per-message named scalars this response stated for `message_id` (A6).

        `(position, internal_date)`, each `None` where the observation recorded nothing.
        Private for exactly the reason `_thread_of` is: answering a per-id question for an
        arbitrary string is a membership oracle over the sealed page, and the ledger is the
        only caller.
        """
        return self._positions.get(message_id), self._internal_dates.get(message_id)

    def _thread_facts(self) -> tuple[int | None, str | None, str | None]:
        """The thread-level named scalars this response stated (A6).

        `(stated_total, history_id, fetched_at)`. These belong to the response rather than
        to any one id, which is why they travel separately from `_scalars_of`.
        """
        return self._stated_total, self._history_id, self._fetched_at

    @property
    def page_size(self) -> int | None:
        """The page size a listing call was made with; `None` for the other endpoints."""
        return self._page_size

    @property
    def more_pages(self) -> bool:
        return self._more_pages

    @property
    def next_page_token(self) -> str | None:
        """Gmail's opaque continuation token; carries no message identity."""
        return self._next_page_token

    @property
    def recorded(self) -> bool:
        """Whether a ledger has already taken this observation's ids.

        Two answers, and the disjunction is the point (R-ARCH-036). `_consumed` is an
        ordinary slot: it travels with a `copy.copy`, which is why a copy of a recorded page
        is still refused - and it is re-armable, because `object.__setattr__(page,
        "_consumed", False)` writes it back to `False` and the refusal below then does not
        fire. `_RECORDED` is held against the object where the object cannot restate it, so
        it survives that write; it does **not** travel with a copy, which is why the slot is
        kept rather than replaced. Neither alone is the property.
        """
        return self._consumed or _RECORDED.recall(self) is not None

    def _release(self, token: object) -> tuple[str, ...]:
        """One-shot: an observation is one executed call, and is recorded once.

        R-RETR-003: this set `_consumed` and never read it, so the same object handed to
        `record_list_page` a second time under a different query was accepted and minted a
        second `ScanScopeEntry`. `H` was unaffected - `setdefault` is idempotent - but
        `scan_scope` is the response's account of which queries were *executed*, and two
        entries backed by one call is a false account of the retrieval. A caller that
        really ran the query twice has two observations; a caller replaying one has one.

        R-ARCH-036: the latch was an ordinary slot and `object.__setattr__(page, "_consumed",
        False)` re-armed it, producing exactly the second `scan_scope` entry this refusal says
        it prevents. The latch is now also held in `_RECORDED`, which the object cannot
        restate - see `recorded` for why both halves are kept. This does not touch A1's
        over-recording residue: the constructor is public, so a caller who wants a second
        observation of one call has always been able to build one, and that is bounded by the
        content witness A1 leaves unbuilt rather than by anything here.
        """
        if token is not _RECORD_TOKEN:
            raise DispositionInvariantError(
                "the IDs of a fetched page are readable only by DispositionLedger; a "
                "caller that could read them could record fewer than it fetched, which is "
                "exactly how H comes to be under-counted (AD A.7a, RR EV-01)"
            )
        if self.recorded:
            raise DispositionInvariantError(
                f"this {self._endpoint.value} observation has already recorded its ids; "
                "recording it again would put a second entry in scan_scope for one "
                "executed call, claiming a query returned ids it never ran to get "
                "(AD A.7a, R-RETR-003)"
            )
        self._consumed = True
        _RECORDED.remember(self, True)
        return self._ids

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"FetchedIds(endpoint={self._endpoint.value}, size={len(self._ids)}, "
            f"more_pages={self._more_pages}, recorded={self._consumed})"
        )


_RECORDED: Final[IdentityRegistry[bool]] = IdentityRegistry(
    "fetched pages whose ids a DispositionLedger has already taken"
)
"""Which observations have been recorded, held where the observation cannot restate it.

`FetchedIds._consumed` is a slot, and a slot is writable by `object.__setattr__` whatever the
class does about `__setattr__` - which R-ARCH-036 used to re-arm the one-shot latch and put a
second `scan_scope` entry behind one executed call. This is the same primitive the certificate
uses, applied to the one-shot rather than to the facts.
"""


_MINT_TOKEN = object()
"""Private capability token. Only `DispositionLedger.certify` holds it.

**It is the gate on `__init__`, and `__init__` was never the only way in (R-SEC-046).** This
docstring used to say the token made a certificate "unforgeable by accident ... not a defence
against code that deliberately reaches for a private name". Both halves were wrong in the
same direction: forging one needed no private name at all.

    forged = copy.copy(certificate)   # __init__ never runs; no token is presented
    forged._withheld = ()             # a plain attribute assignment - the properties are
    forged._hit_count = 1             #   read-only, the slots behind them were not
    Envelope(..., disposition=forged) # ACCEPTED, stating withheld=[] and partial=false

That is R-SEC-039's defect and round 12's part-3b defect, in the seal invariant I-1 rests on.
What closes it is not a longer list of construction paths but the certified facts no longer
living on the object at all: see `_CERTIFIED` below. The token still guards the mint, because
an early failure at the point somebody writes the mistake is worth having; it is not what
makes a certificate mean anything.
"""


@dataclass(frozen=True)
class AdmissionRoute:
    """One observation that returned an ID: the endpoint, the rung and the query.

    **`HitOrigin` says where an id *entered* `H`; this says every way it was reached**
    (2026-09-15, A16). The two are different questions and only the first was recorded.
    `_admit` keeps an id's origin at its first admission on purpose - "a second sighting does
    not move it" - so an id the L5 recency probe listed first and a lexical rung matched
    afterwards carries an L5 origin for ever. Reading the origin as *the* route is then a
    first-admission artefact, and A16 turns on exactly this distinction: a lexical match keeps
    its evidence protection however many other probes also returned it.

    A **set** of these per id, written on every observation, is what makes "admitted only by
    an internal recency probe" answerable. A set, so two identical observations leave one
    member: the question this answers is *which routes exist*, never how many times each was
    taken, and nothing reads a count. It adds nothing to `H`: the ids are the same ids, and
    `_admit` remains their sole writer.
    """

    endpoint: ObservedEndpoint
    rung: RungId | None
    query: str | None


@dataclass(frozen=True)
class HitOrigin:
    """Where an ID entered `H`. Kept so a reviewer can join `H` back to its cause.

    `endpoint` is carried beside `clause` rather than derived from it at read time: the
    clause is A.7a's vocabulary and the endpoint is the observed fact it was derived from,
    and a reviewer joining `H` against a transcript of executed calls needs the second one.

    `thread_id` is the thread the observation itself put this id in, and since R-DISC-009
    it is *read* as well as written: it is the only source of the thread a withheld record
    is charged against. `None` means the observation recorded no thread for this id.
    """

    clause: str  # "H-lex" | "H-hist" | "H-thr" (A.7a, amendment A2)
    endpoint: ObservedEndpoint
    rung: RungId | None
    query: str | None
    thread_id: str | None = None
    #: Amendment A6's per-message named scalars: the index this response put the message at
    #: in its thread's chronological order, and Gmail's `internalDate` for it. `None` means
    #: the observation recorded neither - not that the message has none - and an envelope
    #: field with no observed value behind it keeps the weaker check it already had.
    position: int | None = None
    internal_date: str | None = None


class ObservedThread(NamedTuple):
    """The thread-level facts one Gmail response stated, sealed at the moment of the call.

    Amendment A6's other half. `stated_total`, `history_id` and `fetched_at` are facts of
    the *response* rather than of any one message, so they are accumulated per thread
    rather than per id. Every field is a bounded scalar (`MAX_SEALED_SCALAR_CHARS`), which
    is what keeps a widened seal from becoming somewhere mail text lives.

    A field is filled once. A later observation of the same thread may supply a fact an
    earlier one did not carry - the ordinary ladder is a `messages.list` page followed by a
    `threads.get` over the same thread - but two observations that *disagree* about the
    same fact are refused rather than resolved, exactly as `HitOrigin.thread_id` is: a
    thread has one length, and picking one of two answers would be inventing evidence.

    **A `NamedTuple` rather than a frozen dataclass (R-ARCH-032).** These objects are handed
    out by `DispositionCertificate.observed_thread_facts` and are read by two of `Envelope`'s
    validators, so a caller holding one that could be written through would be holding the
    ledger's own record of what Gmail said. A frozen dataclass without `slots` keeps an
    instance `__dict__`, and `vars(fact)["stated_total"] = 99` walks past `frozen=True`;
    `slots=True` closes that and leaves `object.__setattr__` open. A `NamedTuple` refuses
    all three, which is established by execution in
    `tests/test_certified_facts_round14.py::test_every_value_a_certificate_hands_back_refuses_to_be_written`
    rather than argued here.
    """

    thread_id: str
    stated_total: int | None = None
    history_id: str | None = None
    fetched_at: str | None = None


@dataclass(frozen=True)
class _WithheldNote:
    """What a cap owes for an id it could not disclose: a reason and a way to get it.

    Deliberately *not* a `WithheldRecord`: a record carries a `thread_id`, and no cap is
    in a position to state one. The record is minted in `certify`, where the thread comes
    from the id's `HitOrigin` (R-DISC-009).
    """

    cap: WithheldCap
    why: str
    affordance: Affordance
    #: **Round 29, R-MCP-033.** At what granularity this withholding is accounted for on the
    #: wire. Filed here, by the cap that fired, because the site that knows *why* it withheld
    #: is the site that knows which call gets the message back: a thread nobody mapped is
    #: recovered by one `mailweave_thread_map`, and forty-five records pointing at that one
    #: call are forty-four repetitions. Defaults to MESSAGE, so a cap that says nothing keeps
    #: the pre-round-29 shape rather than silently collapsing into a count.
    granularity: WithheldGranularity = WithheldGranularity.MESSAGE


def disclosure_digest(ids: Iterable[str]) -> str:
    """A stable digest of a disclosed-ID set, so a certificate binds to one payload."""
    joined = "\n".join(sorted(set(ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _withheld_seal(
    records: tuple[WithheldRecord, ...],
    groups: tuple[WithheldGroup, ...] = (),
    grouped_ids: tuple[str, ...] = (),
    tails: tuple[WithheldTail, ...] = (),
) -> str:
    """A digest of the withheld records *as they were* when `certify` computed them.

    The records are the one thing in `_CertifiedFacts` this module does not own the type of:
    a `WithheldRecord` is a Pydantic model, so it has an instance `__dict__` and
    `vars(record)["id"] = "m9"` walks past `frozen=True` exactly as R-SEC-046's two
    assignments walked past the certificate's read-only properties. Making the *container*
    immutable and trusting what it contains would be this project's own defect - one shape
    sealed, its peers trusted - so the contents are sealed too, by a value the record cannot
    restate.

    The material is each record's own wire form, so a field added to `WithheldRecord` in a
    later round is sealed the day it exists rather than the day somebody remembers to add it
    here. `sort_keys` and a fixed separator make the rendering canonical.
    """
    material = json.dumps(
        {
            "records": [record.model_dump(mode="json") for record in records],
            "groups": [group.model_dump(mode="json") for group in groups],
            "tails": [tail.model_dump(mode="json") for tail in tails],
            "grouped_ids": sorted(grouped_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class _CertifiedFacts(NamedTuple):
    """Everything a certificate states, as `certify` computed it, held off the certificate.

    R-SEC-046's fix was to move the numbers off the certificate: they used to sit in its own
    `__slots__`, so `copy.copy` produced a second certificate carrying them and two plain
    assignments rewrote what it certified. Facts kept here belong to the object `certify`
    minted and to nothing that is merely shaped like it: a copy, a `pickle` round trip, a
    `__reduce_ex__` rebuild or an `object.__new__` shell is a *different object*, so it has
    no facts at all rather than editable ones.

    **R-ARCH-032: that made the record single and left it writable, which is worse.** This
    was a `@dataclass(frozen=True)` with no `slots`, so it kept an instance `__dict__`, and
    the object is one dereference from a certificate any caller already holds:

        facts = certificate._certified
        vars(facts)["withheld"] = ()          # `frozen=True` guards __setattr__, not __dict__
        vars(facts)["hit_count"] = 1

    published `withheld: []` and `partial: false` for a ledger holding an unaccounted hit -
    through the ordinary constructor, with every validator running and passing. Concentrating
    the truth in one place is what makes the design work and is exactly what makes a writable
    record fatal: once it is rewritten every cross-check agrees, `__repr__` reports the lie as
    genuine, and nothing in the process still knows the truth.

    A `NamedTuple` has no `__dict__` and refuses `object.__setattr__`; a
    `@dataclass(frozen=True, slots=True)` closes the first and **not** the second, which is
    established by execution in `tests/test_certified_facts_round14.py` rather than taken from
    a review. Every field below is therefore either an immutable scalar, a tuple of them, or
    sealed by `withheld_seal`; the mappings are held as tuples of pairs and rebuilt on each
    read, so what a property hands back is a copy nobody else is holding.

    It is not a second statement of anything: the certificate has no other copy to disagree
    with, which is why the properties below read from here instead of comparing against here.
    """

    hit_count: int
    disclosed_hits: int
    withheld: tuple[WithheldRecord, ...]
    #: **Round 29, R-MCP-033.** Withholdings written at thread granularity: one entry per
    #: (thread, cap), each carrying an exact count. Sealed with the individual records.
    withheld_groups: tuple[WithheldGroup, ...]
    #: Groups past `MAX_WITHHELD_GROUPS_NAMED`, folded per cap into exact counts (round 29).
    withheld_tail: tuple[WithheldTail, ...]
    #: The ids those groups stand for. Held so `withheld_ids` can still answer with **every**
    #: id the set difference produced - a downstream check that compared `H - disclosed`
    #: against only the named records would otherwise find a residue and be right to.
    grouped_ids: tuple[str, ...]
    #: `_withheld_seal(withheld, groups, grouped_ids)` at the moment `certify` minted it.
    #: The records are Pydantic
    #: models and are therefore the one writable thing reachable from here; this is what makes
    #: a write into one visible.
    withheld_seal: str
    disclosure_digest: str
    observed_threads: tuple[tuple[str, str | None], ...]
    hits_per_rung: tuple[tuple[RungId | None, int], ...]
    observed_scalars: tuple[tuple[str, tuple[int | None, str | None]], ...]
    observed_thread_facts: tuple[tuple[str, ObservedThread], ...]


_CERTIFIED: Final[IdentityRegistry[_CertifiedFacts]] = IdentityRegistry(
    "disposition certificates minted by DispositionLedger.certify"
)
"""What each minted certificate certifies, keyed by that certificate object.

See `mailweave.sealing` for why the key is the object rather than its address, and why a
`WeakKeyDictionary` would not do. The same registry primitive holds the harness's credential
binding, for the same reason and after the same finding.
"""


class DispositionCertificate:
    """Proof that `withheld` was derived from `H` by set difference, not asserted.

    An `Envelope` requires one. It can only be minted by `DispositionLedger.certify`, and it
    carries the digest of the exact disclosed set it was computed against, so a certificate
    cannot be lifted from one response and attached to another.

    **The object holds nothing** (R-SEC-046). Every number below is read from `_CERTIFIED` at
    the moment it is asked for, so there is no state on the instance to copy or to rebuild: a
    certificate that `certify` did not mint does not state a *different* disposition, it
    states none, and every property raises. That is the difference between detecting a forgery
    and having nothing to forge - the check is not somewhere a caller must remember to make
    it, it is the only way the facts can be reached at all.

    **The facts are reachable, and that is why they are immutable** (R-ARCH-032). This
    paragraph used to end "no state on the instance to copy, to rebuild, or to **write
    over**", and the third clause was false. `_certified` is an attribute on an object the
    caller already holds, the record behind it was a frozen dataclass with an ordinary
    instance `__dict__`, and two `vars()` writes rewrote the one authoritative account of what
    `certify` computed. Nothing detected it, because after the write nothing in the process
    disagreed - which is the cost of concentrating the truth in one place, and the reason that
    place has to be unwritable. What is true now is executed in
    `tests/test_certified_facts_round14.py` rather than argued here:

      * the record is a `NamedTuple`, which refuses `vars()`, `setattr` **and**
        `object.__setattr__` - unlike a frozen dataclass, with or without `slots`;
      * every value it holds is an immutable scalar or a tuple of them; the mappings are
        rebuilt on each read, so a caller writes only into their own copy, and there is no
        `mappingproxy` whose underlying dict is one `gc.get_referents` away;
      * the one Pydantic model in there - `WithheldRecord`, which does have a writable
        `__dict__` - is covered by `withheld_seal`, re-derived on every read of `withheld`.

    **And a subclass is not that object** - found by this round's implementer, attacking its
    own fix after the registry landed. Holding the facts off the instance closes every route
    that *rebuilds* a certificate and closes none that **replaces the reader**:

        class Forged(DispositionCertificate):      # three ways: the class statement,
            @property                              # types.new_class, and type.__new__
            def withheld(self): return ()
            @property
            def withheld_ids(self): return frozenset()
        Envelope(..., disposition=object.__new__(Forged))    # was ACCEPTED, and serialised

    `_certified` is never consulted, so nothing raises, and `Envelope`'s field is an
    `isinstance` check that a subclass passes. That is R-RETR's round-3 attack on this
    module's own mint token (`ROUND_03/R-RETR.md`, attack 8) - defeat a token by subclassing
    rather than by reaching for it - which `SeedSession` has refused since round 12 and which
    the certificate did not. Subclassing is refused outright now, here as there.

    The consequences, so they are read rather than discovered:

      * `copy.copy`, `copy.deepcopy` and `pickle` now *succeed* and produce an object that
        answers nothing. Before, two of them happened to raise on a `mappingproxy`, which was
        an artefact protecting nothing - `copy.copy` went straight through it;
      * an unminted certificate is refused wherever it is used rather than only where
        somebody checked, so a future consumer inherits the property without knowing about it;
      * a certificate cannot cross a process boundary, and never could;
      * a **duck-typed impostor** - a class that merely has the same properties - is refused
        by `assert_is_a_minted_certificate`, which every consumer must call. It was **not**
        refused by `Envelope`'s field type, which this paragraph claimed for one round:
        `isinstance` consults `obj.__class__`, so a plain object with a `__class__` property
        returning this class passes it, and R-SEC-054 published `withheld: []` through that
        route with no `DispositionLedger` in the process at all. An `isinstance` check is a
        statement about what an object says it is; the mint is a statement about what this
        process did.

    What this does not establish is stated where both of this project's capability tokens are
    described together, in `mailweave.sealing`: code that imports `_CERTIFIED` and calls
    `remember` mints whatever it likes, and no object in this language can stop it.
    """

    __slots__ = ("__weakref__",)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError(
            "DispositionCertificate may not be subclassed: a subclass overrides the "
            "properties that read the ledger's facts out of the seal registry, so it answers "
            "whatever it likes and the registry is never consulted - which is how R-RETR "
            "defeated this module's mint token in round 3 (attack 8) without reaching for "
            "the token, and is the one route holding the facts off the object does not close "
            "by itself. A certificate comes from DispositionLedger.certify"
        )

    def __init__(
        self,
        token: object,
        *,
        hit_count: int,
        disclosed_hits: int,
        withheld: tuple[WithheldRecord, ...],
        withheld_groups: tuple[WithheldGroup, ...],
        withheld_tail: tuple[WithheldTail, ...],
        grouped_ids: tuple[str, ...],
        digest: str,
        observed_threads: Mapping[str, str | None],
        hits_per_rung: Mapping[RungId | None, int],
        observed_scalars: Mapping[str, tuple[int | None, str | None]],
        observed_thread_facts: Mapping[str, ObservedThread],
    ) -> None:
        if token is not _MINT_TOKEN:
            raise DispositionInvariantError(
                "a disposition certificate may only be minted by DispositionLedger.certify; "
                "constructing one directly would let an envelope claim an invariant it "
                "never computed"
            )
        _CERTIFIED.remember(
            self,
            _CertifiedFacts(
                hit_count=hit_count,
                disclosed_hits=disclosed_hits,
                withheld=withheld,
                withheld_groups=withheld_groups,
                withheld_tail=withheld_tail,
                grouped_ids=grouped_ids,
                withheld_seal=_withheld_seal(withheld, withheld_groups, grouped_ids, withheld_tail),
                disclosure_digest=digest,
                observed_threads=tuple(dict(observed_threads).items()),
                hits_per_rung=tuple(dict(hits_per_rung).items()),
                observed_scalars=tuple(dict(observed_scalars).items()),
                observed_thread_facts=tuple(dict(observed_thread_facts).items()),
            ),
        )

    @property
    def _certified(self) -> _CertifiedFacts:
        """What the ledger computed for *this* object, or a refusal.

        Every property goes through here, which is what makes the check impossible to skip.
        """
        facts = _CERTIFIED.recall(self)
        if facts is None:
            raise DispositionInvariantError(
                "this DispositionCertificate certifies nothing: no ledger minted it. A "
                "certificate's facts are what `certify` computed, held against the object it "
                "minted, so a copy, a rebuild by pickle or __reduce_ex__, or an instance "
                "built without running __init__ carries none of them. Re-run "
                "DispositionLedger.certify against the ledger this response was retrieved "
                "with (AD A.7a, contract I-1, R-SEC-046)"
            )
        return facts

    def assert_minted(self) -> None:
        """Refuse unless a ledger minted *this* object. The named form of the check above.

        Nothing depends on a caller remembering it - every property already fails closed -
        but a consumer that wants the refusal at a place it chose, with a message about the
        certificate rather than about whichever number it asked for first, has this.
        """
        _ = self._certified

    @property
    def hit_count(self) -> int:
        return self._certified.hit_count

    @property
    def disclosed_hits(self) -> int:
        return self._certified.disclosed_hits

    @property
    def withheld(self) -> tuple[WithheldRecord, ...]:
        """The records `certify` minted, or a refusal if one of them has been rewritten.

        The tuple is immutable and the registry's entry cannot be replaced, but a
        `WithheldRecord` is a Pydantic model with an instance `__dict__`, so
        `vars(record)["id"] = "m9"` rewrites what this certificate says about which message
        is missing - and, because the envelope compares its own records against *these same
        objects*, both sides would agree. The seal is re-derived on every read rather than
        checked once somewhere a caller must reach, for the same reason `_certified` is.
        """
        facts = self._certified
        if (
            _withheld_seal(
                facts.withheld, facts.withheld_groups, facts.grouped_ids, facts.withheld_tail
            )
            != facts.withheld_seal
        ):
            raise DispositionInvariantError(
                "a withheld record has been rewritten since certify minted it: this "
                "certificate's records no longer digest to the value sealed with them. A "
                "record carries the id, the thread, the cap, the reason and the affordance "
                "the ledger derived at certification; changing any of them makes the "
                "response's account of what is missing something no set difference computed "
                "(AD A.7a, contract I-1, R-ARCH-032)"
            )
        return facts.withheld

    @property
    def withheld_ids(self) -> frozenset[str]:
        """**Every** id the set difference produced, named or grouped.

        Round 29 split how a withholding is *written* without splitting what it *covers*. A
        consumer asking which ids are missing gets the same answer it got before groups
        existed; a consumer asking which records to render reads `withheld` and
        `withheld_groups`. Keeping the two questions apart is what lets the wire get smaller
        without any check downstream getting weaker.
        """
        facts = self._certified
        named = frozenset(record.id for record in self.withheld)
        return named | frozenset(facts.grouped_ids)

    @property
    def withheld_groups(self) -> tuple[WithheldGroup, ...]:
        """Thread-granular withholdings, sealed with the named records."""
        _ = self.withheld  # re-derives the seal over every half, and refuses on a rewrite
        return self._certified.withheld_groups

    @property
    def withheld_tail(self) -> tuple[WithheldTail, ...]:
        """Groups past the naming bound, folded per cap into counts; sealed with the rest."""
        _ = self.withheld
        return self._certified.withheld_tail

    @property
    def disclosure_digest(self) -> str:
        """Digest of the disclosed-ID set this certificate was computed against."""
        return self._certified.disclosure_digest

    @property
    def observed_threads(self) -> Mapping[str, str | None]:
        """For every id in `H`, the thread the observation put it in (R-DISC-011).

        `None` for an id whose observation recorded no `threadId`; **absent** for an id
        that never entered `H` at all, and the two are different facts. A disclosed row
        for an absent id is a message no executed retrieval returned - which A1's content
        witness bounds and this process cannot - while a disclosed row for a present id
        whose thread disagrees with the source is a message this response *knows* belongs
        somewhere else.

        Carried on the certificate rather than read from the ledger so that the envelope
        checks against the same enumeration the set difference was computed from: a
        certificate lifted from another response already fails the digest check, and it
        now brings its own threads with it rather than letting a second ledger answer.

        A fresh mapping on every read (R-ARCH-032). What used to be returned was the
        registry's own `MappingProxyType`, and a proxy is read-only only to the caller who
        does not reach for the dict behind it - `gc.get_referents(proxy)[0]` is that dict and
        writing into it changes what the proxy reports, which is executed in
        `tests/test_certified_facts_round14.py`. A copy nobody else holds cannot be written
        through to anything.
        """
        return dict(self._certified.observed_threads)

    @property
    def hits_per_rung(self) -> Mapping[RungId | None, int]:
        """How many ids entered `H` at each rung, counted from `HitOrigin.rung`.

        `hit_count_per_rung` is the retrieval report's own account of the hit set, and it
        was the last number about `H` still travelling beside the enumeration rather than
        out of it: `_rung_counts_align` compared its *length* against `rungs` and nothing
        compared its *values* against anything. A response could therefore report
        `[0, 3]` for a ledger holding nine ids, which is R-DISC-001's arithmetic in the one
        block a reader consults to decide whether the numbers add up.

        An id is counted at the rung whose observation admitted it, which is what "found at
        this rung" means: a second sighting at a later rung does not move it, exactly as its
        origin does not move.
        """
        return dict(self._certified.hits_per_rung)

    @property
    def observed_positions(self) -> Mapping[str, int]:
        """For every id in `H` whose observation stated one, its index in its thread (A6).

        **Absent** for an id no observation placed, which is a different fact from position
        zero. `MessageRow.position` was the clearest class-O case in the round 7 audit: the
        row states an index into the `threads.get` response's message order, and the seal
        recorded the order and threw the index away, so A3's `0 <= p < stated_total` was
        the only bound available. Where this mapping has an entry, the envelope now holds
        the row to the observed value exactly.
        """
        return {
            message_id: position
            for message_id, (position, _) in self._certified.observed_scalars
            if position is not None
        }

    @property
    def observed_internal_dates(self) -> Mapping[str, str]:
        """Gmail's `internalDate` for every id in `H` whose observation stated one (A6)."""
        return {
            message_id: internal_date
            for message_id, (_, internal_date) in self._certified.observed_scalars
            if internal_date is not None
        }

    @property
    def observed_thread_facts(self) -> Mapping[str, ObservedThread]:
        """The thread-level named scalars each observed thread stated (amendment A6).

        Keyed by thread id. A thread appears here as soon as any observation named it, even
        if that observation stated none of the scalars, so "the ledger has no opinion about
        this thread" and "the ledger observed this thread and it stated no total" stay
        distinguishable - the same distinction `observed_threads` draws for `None`.
        """
        return dict(self._certified.observed_thread_facts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        facts = _CERTIFIED.recall(self)
        if facts is None:
            return "DispositionCertificate(<certifies nothing: no ledger minted this object>)"
        return (
            f"DispositionCertificate(H={facts.hit_count}, disclosed={facts.disclosed_hits}, "
            f"withheld={len(facts.withheld)})"
        )


def assert_is_a_minted_certificate(candidate: object) -> DispositionCertificate:
    """Refuse anything but a certificate **this process's** `certify` minted (R-SEC-054).

    The one question a consumer has to ask, asked in the two halves that are not the same
    question:

      * `type(candidate) is DispositionCertificate` - the *actual* type, read off the object's
        type slot. `isinstance` was what stood here for one round, and `isinstance` consults
        `obj.__class__` when `type(obj)` does not match, so an ordinary object with

            @property
            def __class__(self): return DispositionCertificate

        passed it, was accepted by `Envelope`, and serialised `withheld: []` / `partial:
        false` for a ledger holding an unaccounted hit - with no `DispositionLedger` in the
        process at all, since `disclosure_digest` is a public function and the attacker
        controls the payload (R-SEC-054). `type(...) is ...` has no such hook: a property
        cannot lie to it, and CPython offers no user-space override of the type slot;
      * `_CERTIFIED.recall(...) is not None` - the object was minted here. `type` alone would
        admit a `copy.copy` of a real certificate, which is the exact class of the same type;
        `recall` alone would admit a duck whose facts somebody `remember`ed, which is the
        residue `sealing.py` already concedes and which needs the module's private name.

    Neither half is redundant and both are asserted by execution. What this deliberately does
    **not** do is ask the candidate anything - no `assert_minted()`, no property read - because
    a forgery is exactly an object that answers questions the way a real one does.
    """
    if type(candidate) is not DispositionCertificate:
        raise DispositionInvariantError(
            "this response's disposition is not a DispositionCertificate: it is a "
            f"{type(candidate).__name__}. The check is on the object's actual type rather "
            "than on `isinstance`, because `isinstance` consults `__class__` and an object "
            "that declares one passes it while certifying nothing (R-SEC-054). A "
            "certificate comes from DispositionLedger.certify (AD A.7a, contract I-1)"
        )
    minted: DispositionCertificate = candidate
    if _CERTIFIED.recall(minted) is None:
        raise DispositionInvariantError(
            "this DispositionCertificate certifies nothing: no ledger minted it. A "
            "certificate's facts are what `certify` computed, held against the object it "
            "minted, so a copy, a rebuild by pickle or __reduce_ex__, or an instance built "
            "without running __init__ carries none of them. Re-run DispositionLedger.certify "
            "against the ledger this response was retrieved with (AD A.7a, contract I-1, "
            "R-SEC-046)"
        )
    return minted


@dataclass
class DispositionLedger:
    """Accumulates `H` as retrieval executes; the only source of truth for the hit set.

    Rungs call `record_list_page` / `record_history_additions` / `record_shortlist`. Caps
    call `note_withheld` to supply the *reason* for an ID they could not disclose - never
    to decide membership, which is computed.
    """

    _origins: dict[str, HitOrigin] = field(default_factory=dict)
    _threads: dict[str, ObservedThread] = field(default_factory=dict)
    _notes: dict[str, _WithheldNote] = field(default_factory=dict)
    #: The call that widens each cap, for groups a response folds into a tail (round 29).
    _tail_recovery: dict[WithheldCap, Affordance] = field(default_factory=dict)
    #: `{thread id: retrieval rank}` for the threads the producer ranked, so the groups and
    #: the not-included entries are written best first (R-M2-096). A thread absent here is
    #: written after every ranked one, by thread id: deterministic, and never a guess.
    _ranks: dict[str, int] = field(default_factory=dict)
    _scan_scope: list[ScanScopeEntry] = field(default_factory=list)
    _shortlist: Shortlist | None = None
    _shortlist_ids: frozenset[str] = frozenset()
    #: `{message id: every observation that returned it}` (A16). Distinct from `_origins`,
    #: which holds the *first* admission and is what the wire reports; this accumulates, so a
    #: question about an id's routes is not silently answered about its earliest one.
    _routes: dict[str, set[AdmissionRoute]] = field(default_factory=dict)

    # -- H accumulation ---------------------------------------------------------------

    def _admit(
        self,
        page: FetchedIds,
        *,
        expected: ObservedEndpoint,
        rung: RungId | None,
        query: str | None,
    ) -> tuple[str, ...]:
        """The one and only way an ID enters `H`. Everything else selects out of it.

        Three properties hold because this is the sole writer of `self._origins`, and all
        three are asserted by tests rather than left as prose:

          * every ID in `H` was released from a `FetchedIds` observation, i.e. it is an ID
            an executed Gmail call actually returned;
          * no public method can grow `H` from a collection the caller assembled;
          * the A.7a clause an ID enters under is read off the observation's endpoint, not
            supplied by the caller. `expected` is the endpoint the *intake* is for, and a
            mismatch is refused: recording a `threads.get` response through
            `record_list_page` would otherwise mint a `scan_scope` entry describing a
            `messages.list` query that was never executed (amendment A2).
        """
        if page.endpoint is not expected:
            raise DispositionInvariantError(
                f"a {page.endpoint.value} observation cannot be recorded as a "
                f"{expected.value} one: the clause an id enters H under is decided by the "
                "call that returned it, and relabelling it would put a query in scan_scope "
                "that never ran (AD A.7a, amendment A2)"
            )
        clause = CLAUSE_BY_ENDPOINT[page.endpoint]
        stated_total, history_id, fetched_at = page._thread_facts()
        materialised = page._release(_RECORD_TOKEN)
        for message_id in materialised:
            observed_thread = page._thread_of(message_id)
            position, internal_date = page._scalars_of(message_id)
            if observed_thread is not None:
                self._record_thread_facts(
                    thread_id=observed_thread,
                    stated_total=stated_total,
                    history_id=history_id,
                    fetched_at=fetched_at,
                    endpoint=page.endpoint,
                )
            # **Every observation, not only the first** (A16). Recorded before the branch
            # below so a repeat sighting - which deliberately does not move the origin - is
            # still a route this id has.
            self._routes.setdefault(message_id, set()).add(
                AdmissionRoute(endpoint=page.endpoint, rung=rung, query=query)
            )
            existing = self._origins.get(message_id)
            if existing is None:
                self._origins[message_id] = HitOrigin(
                    clause=clause,
                    endpoint=page.endpoint,
                    rung=rung,
                    query=query,
                    thread_id=observed_thread,
                    position=position,
                    internal_date=internal_date,
                )
                continue
            existing = self._merge_scalars(message_id, existing, position, internal_date)
            self._origins[message_id] = existing
            # An id is admitted once - its origin is where it *entered* `H`, and a second
            # sighting does not move it. Its thread is the one exception, because a later
            # call can observe a fact the earlier one did not carry: the ordinary ladder is
            # a `messages.list` page followed by a `threads.get` over the same thread, and
            # without this an id first seen on a page that recorded no `threadId` could
            # never be withheld even though a later observation named its thread.
            if observed_thread is None or observed_thread == existing.thread_id:
                continue
            if existing.thread_id is not None:
                raise DispositionInvariantError(
                    f"two observations disagree about which thread {message_id!r} is in: "
                    f"{existing.endpoint.value} said {existing.thread_id!r} and "
                    f"{page.endpoint.value} says {observed_thread!r}. A message belongs to "
                    "one thread, so one of these responses was not what it claims to be - "
                    "and the disagreement cannot be resolved by picking one (R-DISC-009)"
                )
            self._origins[message_id] = replace(existing, thread_id=observed_thread)
        return materialised

    def _record_thread_facts(
        self,
        *,
        thread_id: str,
        stated_total: int | None,
        history_id: str | None,
        fetched_at: str | None,
        endpoint: ObservedEndpoint,
    ) -> None:
        """Fold amendment A6's thread-level scalars into what this ledger has observed.

        A field is filled once and never overwritten. A later observation may supply a fact
        an earlier one did not carry; two observations that **disagree** are refused, for
        the reason `_admit` refuses two threads for one id: a thread has one length and one
        `historyId`, so a disagreement means one of the two responses was not what it
        claims to be, and it cannot be resolved by picking one.

        `fetched_at` is the exception and is deliberately *first-wins without a
        disagreement check*: two calls really are made at two different times, and the
        stamp a source reports is the time its own thread was fetched. Recording the
        earliest keeps the freshness claim conservative - it can only make a response look
        staler than it is, never fresher.
        """
        known = self._threads.get(thread_id, ObservedThread(thread_id=thread_id))
        for name, incoming in (("stated_total", stated_total), ("history_id", history_id)):
            held = getattr(known, name)
            if incoming is None or held is None or held == incoming:
                continue
            raise DispositionInvariantError(
                f"two observations disagree about {name} for thread {thread_id!r}: one "
                f"said {held!r} and this {endpoint.value} says {incoming!r}. A thread has "
                "one of each, so one of these responses was not what it claims to be - and "
                "the disagreement cannot be resolved by picking one (amendment A6, "
                "R-DISC-009's rule applied to the scalars A6 seals)"
            )
        self._threads[thread_id] = ObservedThread(
            thread_id=thread_id,
            stated_total=known.stated_total if known.stated_total is not None else stated_total,
            history_id=known.history_id if known.history_id is not None else history_id,
            fetched_at=known.fetched_at if known.fetched_at is not None else fetched_at,
        )

    def _merge_scalars(
        self,
        message_id: str,
        existing: HitOrigin,
        position: int | None,
        internal_date: str | None,
    ) -> HitOrigin:
        """Fill a per-message scalar a later observation carried and an earlier one did not.

        Same rule as the thread: fill an absent fact, refuse a contradiction. A message sits
        at one index of one thread and has one `internalDate`; two responses stating
        different ones is not a merge conflict to resolve, it is evidence that one of them
        is wrong, and this process cannot tell which (amendment A6, and A1 for why).
        """
        for name, incoming in (("position", position), ("internal_date", internal_date)):
            held = getattr(existing, name)
            if incoming is None or held is None or held == incoming:
                continue
            raise DispositionInvariantError(
                f"two observations disagree about {name} for message {message_id!r}: one "
                f"said {held!r} and another says {incoming!r}. A message has one position "
                "in its thread and one internalDate (A.7a, amendment A6)"
            )
        return replace(
            existing,
            position=existing.position if existing.position is not None else position,
            internal_date=(
                existing.internal_date if existing.internal_date is not None else internal_date
            ),
        )

    def record_list_page(
        self,
        page: FetchedIds,
        *,
        rung: RungId,
        query: str,
        affordance: Affordance | None = None,
        pages_fetched: int = 1,
    ) -> ScanScopeEntry:
        """Clause H-lex: every ID returned by an executed `messages.list`, at any rung.

        This includes the L2/L3 relaxation and broadening queries and the L5 pool
        participant probes - they are `messages.list` calls like any other, and EV-01
        names them explicitly.

        The page is the transport's own record of the call, so `ids_returned`,
        `page_size` and `more_pages` are read off it rather than accepted from the
        caller: a scan-scope entry cannot understate the page it describes.
        """
        materialised = self._admit(
            page, expected=ObservedEndpoint.MESSAGES_LIST, rung=rung, query=query
        )
        page_size = page.page_size
        if page_size is None:  # pragma: no cover - the constructor refuses such a page
            raise DispositionInvariantError(
                "a messages.list observation reached the ledger without a page size"
            )
        entry = ScanScopeEntry(
            q=query,
            rung=rung,
            page_size=page_size,
            pages_fetched=pages_fetched,
            ids_returned=len(materialised),
            more_pages=page.more_pages,
            affordance=affordance,
        )
        self._scan_scope.append(entry)
        return entry

    def record_history_additions(self, page: FetchedIds) -> None:
        """Clause H-hist: every `messagesAdded[].message.id` from `history.list`.

        Same seal as `record_list_page`: the additions arrive as a sealed page from the
        transport, not as a list the caller assembled.
        """
        self._admit(page, expected=ObservedEndpoint.HISTORY_LIST, rung=RungId.LR, query=None)

    def record_thread(self, observation: FetchedIds, *, rung: RungId) -> int:
        """Clause H-thr: every message row a `threads.get` response returned (A2).

        AD D.5 builds the semantic candidate pool thread-wise - "each thread costs one
        `threads.get(format=metadata)` and yields **all** its message rows" - and its
        first-priority source is threads already touched by earlier rungs. Those rows reach
        the pool through this endpoint and no other, so before amendment A2 a top-k drawn
        from them would have been refused by `record_shortlist` as unprovenanced: the seal
        would have rejected WS-08's own first-choice input.

        Same seal as the two listing intakes, and for the same reason: the ids arrive
        inside a sealed observation minted by the call, never as a list a caller assembled,
        and the clause is read off the endpoint rather than asserted here.

        No `ScanScopeEntry` is appended. `scan_scope` is defined per executed *query* and a
        `threads.get` has none; giving it one would mean inventing a `q` and a `page_size`
        that no call ever carried, which is the shape of dishonesty this module exists to
        refuse. A thread observation is therefore visible in `origins` (with its
        `thread_id`) and in the trace's call transcript, not in `scan_scope`.

        Returns the number of ids the thread contributed, which is a count, not an ID.
        """
        return len(
            self._admit(observation, expected=ObservedEndpoint.THREADS_GET, rung=rung, query=None)
        )

    def record_shortlist(self, *, ids: Iterable[str], rule: str, k: int) -> Shortlist:
        """Clause H-sem: the declared shortlist, *selected out of* `H` - never added to it.

        `rule` and `k` are pre-registered parameters reported in the retrieval report, so
        `|H|` cannot be shrunk at review time to make the invariant pass (EV-01 i). H1b
        adds the other direction: `|H|` cannot be *stretched* here either, because this
        method does not admit IDs. Three refusals, all at intake:

          * an ID listed twice - a shortlist is a selection, and counting one candidate
            twice is R-RETR-001's arithmetic in a second place;
          * an ID that is not already in `H` - no sealed observation of an executed Gmail
            call returned it, so nothing retrieved it and no evidence backs it;
          * more distinct IDs than the declared `k`.

        Rejecting unprovenanced IDs *here* rather than at `certify` is the point. At
        certification a fabricated ID is indistinguishable from a real one that a cap
        dropped, so the only question left to ask is whether a note was filed - and the
        attacker files the note. At intake the question is answerable from the ledger's
        own enumeration, and the answer cannot be supplied by the caller.
        """
        materialised = list(ids)
        unique = set(materialised)
        if len(unique) != len(materialised):
            counted = Counter(materialised)
            repeats = sorted(mid for mid, times in counted.items() if times > 1)
            raise DispositionInvariantError(
                f"shortlist lists the same id more than once: {repeats}. A shortlist is a "
                "selection of distinct candidates; counting one twice inflates the "
                "declared size against the set it is meant to enumerate."
            )
        unprovenanced = unique - self.hit_ids
        if unprovenanced:
            raise DispositionInvariantError(
                "shortlisted ids never entered H through an executed retrieval: "
                f"{sorted(unprovenanced)}. A shortlist ranks what was fetched; it cannot "
                "introduce a message id of its own. Every id must already be in H via a "
                "sealed observation of an executed Gmail call: a messages.list page "
                "(H-lex), a history addition (H-hist) or a threads.get response (H-thr) "
                "(AD A.7a, amendment A2, contract I-1, RR EV-01)."
            )
        if len(unique) > k:
            raise DispositionInvariantError(
                f"shortlist of {len(unique)} ids exceeds the declared k={k}; "
                "the declared selection rule is what defines H_sem"
            )
        self._shortlist_ids = frozenset(unique)
        self._shortlist = Shortlist(rule=rule, k=k, size=len(unique))
        return self._shortlist

    # -- cap reasons ------------------------------------------------------------------

    def note_withheld(
        self,
        *,
        message_id: str,
        cap: WithheldCap,
        why: str,
        affordance: Affordance,
        granularity: WithheldGranularity = WithheldGranularity.MESSAGE,
    ) -> None:
        """Record *why* a cap could not disclose `message_id`.

        This does not decide membership of `withheld`; `certify` does, by set difference.
        A note that turns out to be unnecessary (because the ID was disclosed after all)
        is an error at certification, not a silently accepted duplicate.

        **It also does not decide which thread the record is charged against** (R-DISC-009).
        Round 5 took `thread_id` here as an ordinary argument and wrote it onto the record
        unread, so a map of thread A could reach `accounted_for == stated_total` by naming
        a real withheld id belonging to thread B: the id existed, a record backed it, and
        nothing ever compared the claim with the `threads.get`/`messages.list` response that
        returned the id. R-DISC executed exactly that, and an ordinary caller bug - the
        wrong `thread_id` in a loop over threads - produces it silently.

        So the parameter is gone rather than cross-checked. A note is the cap's reason and
        nothing else; the thread is read off the observation at `certify`, which is the
        same rule the rest of this module runs on - the claim is derived from the
        enumeration instead of asserted beside it.

        **`granularity` is the one thing the cap does decide** (round 29, R-MCP-033), because
        it is the one thing only the cap knows: which call gets this message back. A cap whose
        remedy names a message keeps MESSAGE and gets a record of its own. A cap whose remedy
        names a thread - the thread was never mapped, or the whole source left - says THREAD,
        and `certify` collapses its ids into one counted group per (thread, cap). It is still
        the set difference that decides *membership*; this decides only how membership is
        written down.
        """
        self._notes[message_id] = _WithheldNote(
            cap=cap, why=why, affordance=affordance, granularity=granularity
        )

    def withdraw_notes(self, message_ids: Iterable[str]) -> None:
        """Take back notes a producer filed for an arrangement it did not serve.

        **Navigation redesign (2026-09-14).** The expansion path builds a response, measures
        it as rendered, and builds a smaller one when the render is over the host's cap. Each
        build files the notes its arrangement implies, and `certify` refuses a note for an id
        the served arrangement discloses - rightly. So the producer withdraws what the trial
        it abandoned filed, and files what the arrangement it serves implies.

        This cannot hide an omission: `certify` still computes `withheld := H - disclosed` by
        set difference and refuses any withheld id that has no note, so a note withdrawn for
        an id that stays withheld makes the response unbuildable rather than quietly smaller.
        """
        for message_id in message_ids:
            self._notes.pop(message_id, None)

    def note_rank(self, thread_id: str, rank: int) -> None:
        """The retrieval rank the producer held `thread_id` at (R-M2-096).

        Read when the withheld groups and the not-included entries are written, so a
        client walking a response's offers walks them in the order retrieval put them in.
        Filed by the producer that ranked, never derived here; a thread never ranked has no
        entry and sorts after every ranked thread, by id.
        """
        self._ranks[thread_id] = rank

    @property
    def ranks(self) -> Mapping[str, int]:
        return MappingProxyType(dict(self._ranks))

    def note_tail_recovery(self, cap: WithheldCap, affordance: Affordance) -> None:
        """The call that widens `cap`, for the groups a response folds into a tail (round 29).

        Only the producer knows it - a wider search carries the caller's query - so it is
        filed here and read at `certify`. A cap with no widening call filed never folds: its
        groups are all named, however many, because a tail with no way out of it is a count
        with no recovery, which contract R-07 forbids.
        """
        self._tail_recovery[cap] = affordance

    # -- views ------------------------------------------------------------------------

    @property
    def hit_ids(self) -> frozenset[str]:
        """`H`."""
        return frozenset(self._origins)

    @property
    def origins(self) -> Mapping[str, HitOrigin]:
        return dict(self._origins)

    @property
    def hits_per_rung(self) -> Mapping[RungId | None, int]:
        """How many ids entered `H` at each rung, counted from `HitOrigin.rung`.

        **One arithmetic, read from two places.** `DispositionCertificate.hits_per_rung` is
        this, carried on the certificate so the envelope checks the report against the
        enumeration the set difference was computed from. A producer that needs the same fact
        before it certifies - `assemble` asks whether L5's probes admitted anything, R-M2-113 -
        reads it here rather than counting the origins again, because two derivations of one
        number are two numbers.
        """
        return Counter(origin.rung for origin in self._origins.values())

    @property
    def routes(self) -> Mapping[str, frozenset[AdmissionRoute]]:
        """Every observation that returned each id (A16), not only the one that admitted it.

        A reader asking "was this id ever matched by a lexical rung" must ask this and not
        `origins`, which answers a different question: which call was *first*.
        """
        return {message_id: frozenset(routes) for message_id, routes in self._routes.items()}

    @property
    def observed_thread_facts(self) -> Mapping[str, ObservedThread]:
        """Amendment A6's thread-level scalars, per thread this ledger has observed."""
        return dict(self._threads)

    @property
    def scan_scope(self) -> tuple[ScanScopeEntry, ...]:
        return tuple(self._scan_scope)

    @property
    def shortlist(self) -> Shortlist | None:
        return self._shortlist

    @property
    def shortlist_ids(self) -> frozenset[str]:
        """The IDs the declared shortlist selected. Always a subset of `H` (H1b).

        Kept separately from `origins` on purpose: an ID's *origin* is where it entered
        `H`, which is the join a reviewer needs, and shortlisting does not change that.
        """
        return self._shortlist_ids

    @property
    def noted_ids(self) -> frozenset[str]:
        return frozenset(self._notes)

    # -- certification ----------------------------------------------------------------

    def _record_for(self, message_id: str) -> WithheldRecord:
        """Mint one withheld record, with its thread read off where the id was observed.

        R-DISC-009. The three other numbers in a response are already derived rather than
        asserted; the thread on a withheld record was the last claim still travelling
        beside the enumeration instead of out of it. `HitOrigin.thread_id` is what the
        Gmail response that returned this id said about it, so it is what the record says.

        An id observed under no thread cannot be given one here. Refusing is the only
        honest option: guessing the thread from the source that wants to count it is
        precisely the borrowing this fix exists to stop, and the reader has no way to tell
        a guessed thread from an observed one.
        """
        note = self._notes[message_id]
        origin = self._origins[message_id]
        if origin.thread_id is None:
            raise DispositionInvariantError(
                f"no thread was observed for withheld id {message_id!r}: it entered H "
                f"through {origin.endpoint.value} ({origin.clause}) and that observation "
                "recorded no threadId for it, so this response cannot say which thread is "
                "missing a message. Record the observation with the threadId Gmail "
                "returned beside the id - a withheld record's thread is derived from where "
                "the id was seen, never supplied beside it (R-DISC-009, PART-05, R-06)."
            )
        return WithheldRecord(
            id=message_id,
            thread_id=origin.thread_id,
            cap=note.cap,
            why=note.why,
            affordance=note.affordance,
        )

    def _write_down(
        self, withheld_ids: frozenset[str]
    ) -> tuple[
        tuple[WithheldRecord, ...],
        tuple[WithheldGroup, ...],
        tuple[WithheldTail, ...],
        tuple[str, ...],
    ]:
        """Split the withheld set into named records and counted groups (round 29).

        **Membership is not decided here** - `certify` already decided it by set difference,
        and this receives the answer. What is decided here is how each id is written down, and
        the decision was made by the cap that filed the note, in `granularity`: a cap whose
        remedy names a message gets a record naming that message; a cap whose remedy names a
        thread contributes to that thread's count.

        Grouping is by `(thread, cap)` and not by thread alone, because two caps that fired on
        one thread are two different statements with two different ways out, and a group that
        merged them would have to pick one `why` and one affordance - which is the kind of
        collapse that makes an omission list unreadable. The `why` is the first note's, and
        every note in a group shares a cap, so it is a sentence about that cap.

        The returned ids are exactly the ids the groups stand for, so `certify` can check that
        the two halves together cover the whole difference and nothing twice.
        """
        named: list[WithheldRecord] = []
        by_group: dict[tuple[str, WithheldCap], list[str]] = {}
        for message_id in sorted(withheld_ids):
            note = self._notes[message_id]
            if note.granularity is WithheldGranularity.MESSAGE:
                named.append(self._record_for(message_id))
                continue
            origin = self._origins[message_id]
            if origin.thread_id is None:
                # A thread-granular record with no thread is a contradiction, and guessing one
                # is the borrowing R-DISC-009 exists to stop. `_record_for` raises with the
                # message that explains it; there is no second, quieter path to the same lie.
                named.append(self._record_for(message_id))
                continue
            by_group.setdefault((origin.thread_id, note.cap), []).append(message_id)

        grouped: list[str] = [member for members in by_group.values() for member in members]

        def group_of(key: GroupKey) -> WithheldGroup:
            # A group of one is a group. The first build wrote it as a record on the theory
            # that it would be cheaper; the wire says otherwise (`constants.py`, R-V01-007).
            thread_id, cap = key
            members = by_group[key]
            first = self._notes[members[0]]
            return WithheldGroup(
                thread_id=thread_id,
                cap=cap,
                why=first.why,
                message_count=len(members),
                affordance=first.affordance,
                rank=self._ranks.get(thread_id),
            )

        # **The arrangement is `envelope.grouping.arrange_groups`'s, the same call the
        # layout charged** (R-M2-094): every group under a cap with no widening call is
        # named, always - a count with no way out is not an omission record, it is a number;
        # past the naming bound the foldable groups take the room the fixed ones leave and
        # the rest fold, one tail per cap. Named groups are written in retrieval rank
        # (R-M2-096). Every folded id stays in `grouped`, so `withheld_ids` and the sum
        # assertion in `certify` are over the whole set still.
        arrangement = arrange_groups(
            by_group, foldable=frozenset(self._tail_recovery), rank_of=self._ranks
        )
        groups = [group_of(key) for key in arrangement.named]
        tails: list[WithheldTail] = []
        for cap in arrangement.tails:
            folded = [group_of(key) for key in arrangement.folded[cap]]
            tails.append(
                WithheldTail(
                    cap=cap,
                    why=folded[0].why,
                    thread_count=len(folded),
                    message_count=sum(group.message_count for group in folded),
                    affordance=self._tail_recovery[cap],
                )
            )
        return tuple(named), tuple(groups), tuple(tails), tuple(sorted(grouped))

    def certify(self, disclosed: Iterable[str]) -> DispositionCertificate:
        """Compute `withheld := H - disclosed` and prove `H == disclosed union withheld`.

        Raises `DispositionInvariantError` - never returns a partial answer - if any of
        the three residues described in the module docstring is non-empty.

        The checks below raise explicitly instead of using `assert`, because `assert` is
        removed by `python -O` and this invariant must hold in every build.
        """
        hits = self.hit_ids
        disclosed_ids = frozenset(disclosed)
        disclosed_hits = hits & disclosed_ids
        withheld_ids = hits - disclosed_ids  # <-- the set difference of A.7a

        unexplained = withheld_ids - self.noted_ids
        if unexplained:
            raise DispositionInvariantError(
                "hits left the payload with no withheld record: "
                f"{sorted(unexplained)}. A cap dropped a retrieved message and did not "
                "say which cap or offer an affordance (AD A.7a, contract I-1, RR EV-01/EV-03)."
            )

        stale = self.noted_ids & disclosed_ids
        if stale:
            raise DispositionInvariantError(
                "withheld records were filed for messages that are disclosed: "
                f"{sorted(stale)}. Depth reduction is not omission (AD A.7a); a stub row "
                "is disclosed, so a withheld record for it is false."
            )

        alien = self.noted_ids - hits
        if alien:
            raise DispositionInvariantError(
                "withheld records were filed for ids that are not in H: "
                f"{sorted(alien)}. Either a rung fetched ids without recording them in the "
                "ledger, in which case H is under-counted and the invariant would pass "
                "vacuously, or the record names the wrong id."
            )

        if hits != (disclosed_hits | withheld_ids):
            raise DispositionInvariantError(  # pragma: no cover - unreachable by construction
                "H != disclosed union withheld after the set difference; the ledger is corrupt"
            )

        records, groups, tails, grouped_ids = self._write_down(withheld_ids)
        covered = (
            len(records)
            + sum(group.message_count for group in groups)
            + sum(tail.message_count for tail in tails)
        )
        if covered != len(withheld_ids):
            raise DispositionInvariantError(  # pragma: no cover - unreachable by construction
                f"the withheld half of this response accounts for {covered} of "
                f"{len(withheld_ids)} withheld messages. Round 29 lets a withholding be "
                "written as a counted group instead of one record per message; it does not "
                "let one go unwritten. Named records plus group counts must equal the set "
                "difference exactly (AD A.7a, contract I-1, R-MCP-033 requirement 7)."
            )
        return DispositionCertificate(
            _MINT_TOKEN,
            hit_count=len(hits),
            disclosed_hits=len(disclosed_hits),
            withheld=records,
            withheld_groups=groups,
            withheld_tail=tails,
            grouped_ids=grouped_ids,
            digest=disclosure_digest(disclosed_ids),
            # R-DISC-011: the withheld half of the payload has taken its thread from here
            # since R-DISC-009; the disclosed half never did. The same enumeration travels
            # with the certificate so `Envelope` can hold a disclosed row to the thread the
            # observation put it in, instead of to the thread the source asserts.
            observed_threads={mid: origin.thread_id for mid, origin in self._origins.items()},
            hits_per_rung=self.hits_per_rung,
            # Amendment A6: the named scalars travel with the certificate for the same
            # reason `observed_threads` does - the envelope checks against the enumeration
            # the set difference was computed from, not against a second ledger's answer.
            observed_scalars={
                mid: (origin.position, origin.internal_date)
                for mid, origin in self._origins.items()
            },
            observed_thread_facts=dict(self._threads),
        )
