"""Minting and verifying a `map_id` (AD A.10, contract MCP-02, rubric MCP-06).

A `map_id` is a **self-describing** handle: base64url of a canonical JSON payload, a dot,
and a base64url HMAC-SHA256 over the encoded payload bytes. There is no server-side session
(SC §14), so everything redemption needs is inside the handle - and everything inside it is
therefore attacker-supplied until the signature has been checked.

**Verified, not trusted**, and the order that phrase implies is the whole of this module:

  1. split and decode. A handle that is not two base64url segments carrying a JSON object of
     the declared shape is `handle_invalid`, and the refusal names fields rather than values
     for the reason `mailweave.validation` gives - the document is caller-supplied, and a
     report that quotes what it refused is a report that echoes whatever was sent;
  2. read `key_epoch` from the *unverified* payload and compare it with the key this server
     holds. It has to be read before the signature is checked, because with the old key gone
     the signature cannot verify either way, and "your handle predates a key rotation" is a
     different fact from "your handle is corrupt" with a different remedy. Nothing else is
     read from the payload at this point, and a forged epoch buys an attacker one error
     class rather than another;
  3. verify the HMAC with `hmac.compare_digest`, over the encoded payload **as received** -
     not over a re-encoding of the parsed object, which would compare a canonicalisation
     against a signature made over the original bytes and would accept two payloads under
     one signature;
  4. check the account. A handle minted for one mailbox is `handle_invalid` against another:
     the signature proves *this server* minted it, and the account hash proves it minted it
     for the mailbox now being served;
  5. check the TTL against `fetched_at`, which is when the maps were read.

Steps 1-5 are AD A.10's step 1, and they touch no network at all. `redeem` does the rest.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mailweave.constants import GMAIL_NUMERIC_ID_RE, MAX_GMAIL_NUMERIC_ID_DIGITS
from mailweave.envelope.disposition import MAX_SEALED_ID_CHARS
from mailweave.envelope.vocab import ToolName
from mailweave.envelope.wire import Affordance, parse_instant
from mailweave.errors import ErrorCode, HandleRefused
from mailweave.handles.keys import HandleKey
from mailweave.validation import failure_summary

#: The handle payload schema version. Present so a payload shape change is a refusal rather
#: than a misreading; bumping it invalidates outstanding handles as `handle_invalid`. 2 since
#: 2026-09-15: the payload carries `page_sizes`, the width each named thread's map was paged
#: at when the handle was minted, so a `thread_map(map_id, page)` can refuse a page whose
#: positions the width no longer places (continuation correctness).
HANDLE_VERSION: Final[int] = 2

#: How long a handle stays redeemable, in seconds. **[DESIGN]** - AD A.10 fixes the LRU's TTL
#: at 60 s and says the handle's own must be at least that, and fixes no number for this one.
#: Fifteen minutes is chosen to be long enough that an agent's follow-up call inside one
#: conversation is never refused for age, and short enough that a handle is not a durable
#: reference to a mailbox state nobody re-verified. It is a floor on nothing: expiry is not a
#: staleness check, and `handle_expired` says only that this handle is too old to be worth
#: re-verifying, never that the mailbox is unchanged.
HANDLE_TTL_SECONDS: Final[int] = 900

#: The shortest TTL a handle may carry. It is the LRU's own TTL, because a handle that
#: expired sooner than the cache entry it is served from would let the cache outlive the
#: right to read it (AD A.10: "always <= the handle TTL").
MIN_HANDLE_TTL_SECONDS: Final[int] = 60

#: The most threads one handle may name. A handle is a map affordance for the sources of one
#: response, and `MAX_HIT_THREADS + MAX_SOURCE_THREADS` is what one response can carry; the
#: bound is here so a decoded payload cannot make redemption fetch an unbounded number of
#: threads before anything has checked how many it asked for.
MAX_HANDLE_THREADS: Final[int] = 16

#: The longest `map_id` this module will even look at, in characters. A bound before any
#: parsing, so a multi-megabyte argument is refused rather than decoded.
MAX_HANDLE_CHARS: Final[int] = 8192

_SEPARATOR: Final[str] = "."

#: A thread id inside a handle payload, bounded exactly where the disposition seal bounds one.
#: The bound is imported rather than restated for the reason `GmailId` imports it: a value that
#: parsed here and was refused two layers down would be an internal error raised because a
#: *caller* sent something unexpected. It matters more here than there: this document is
#: caller-supplied, so without a per-element bound a "thread id" could be a megabyte of prose
#: on its way into a refusal message or an affordance.
HandleThreadId = Annotated[str, Field(min_length=1, max_length=MAX_SEALED_ID_CHARS)]

#: A `historyId` inside a handle payload. Bounded at the length Gmail's own shape allows, so
#: the numeric check in the validator below is never handed an unbounded string to scan.
HandleHistoryId = Annotated[str, Field(min_length=1, max_length=MAX_GMAIL_NUMERIC_ID_DIGITS)]

#: A page width inside a handle payload: at least one position, and no wider than an
#: unsigned 64-bit count - the bound `widest_handle_chars` charges it at.
HandlePageSize = Annotated[int, Field(ge=1, le=2**64 - 1)]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    """Decode one unpadded base64url segment, or raise `binascii.Error`.

    Padding is restored rather than required, which is the same rule the content pipeline
    applies to Gmail's own base64url bodies: an unpadded encoding is the conventional one for
    a token, and refusing it would refuse handles this module itself mints.
    """
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class HandlePayload(BaseModel):
    """What a `map_id` says about itself. Every field is checked before any of it is used.

    `hide_input_in_errors` for the reason `SecretBearingModel` carries it: this document
    comes from the caller, so a report that renders `input_value=...` renders whatever was
    sent - and a handle is the one tool argument an agent will paste from somewhere else.
    The refusal built from it names field paths and error types only.

    Not a `SealedModel`: nothing here reaches the response wire. The handle *string* does,
    and it is opaque.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    v: int
    key_epoch: int = Field(ge=0)
    account_hash: str = Field(min_length=1, max_length=128)
    thread_ids: tuple[HandleThreadId, ...] = Field(min_length=1, max_length=MAX_HANDLE_THREADS)
    #: Each named thread's own `historyId` at the moment it was fetched, positionally
    #: aligned with `thread_ids`.
    #:
    #: **A.10's field list does not name this and it has to be here**, for two reasons that
    #: are the same reason. A.10 keys the LRU on `(thread_id, history_id_at_fetch)`, and MCP
    #: is stateless (SC §14): with no server-side session there is nowhere else
    #: `history_id_at_fetch` could come from, so a handle without it cannot form the key
    #: A.10 specifies. And the liveness probe needs a floor per thread: `history_id` below
    #: is the mailbox watermark observed before the fetch, low enough that no change to any
    #: named thread slips under it, which means the window it walks necessarily also
    #: contains changes already reflected in the map the handle was minted over. Without a
    #: per-thread floor those count, and a freshly minted handle over a mailbox that moved
    #: at all redeems as `handle_stale` - a false staleness claim on first use.
    #:
    #: It is inside the signed payload like everything else, so it is verified, not trusted.
    thread_history_ids: tuple[HandleHistoryId, ...] = Field(
        min_length=1, max_length=MAX_HANDLE_THREADS
    )
    fetched_at: str = Field(min_length=1, max_length=64)
    #: The watermark the liveness probe walks from: the **mailbox** `historyId` observed
    #: before this response fetched any of the threads above (amendment **A10**).
    #:
    #: It used to be `min(thread_history_ids)`, and that was sound and unbounded. A thread's
    #: own `historyId` is the id of the last change that touched *that thread*, so a handle
    #: over a thread nobody has written to since April made the server walk from April - a
    #: window whose length is the thread's quietness rather than the handle's ttl. With
    #: Gmail's 100-record page default and one page per redemption, R-RETR measured 150
    #: unrelated mailbox changes making **every** redemption `handle_stale_unverifiable`
    #: with the LRU permanently bypassed at two calls (R-RETR-060).
    #:
    #: **Why a watermark observed *before* the fetch is the sound one, stated as the two
    #: directions it can be wrong.** Too low costs only work. Too high hides changes: a
    #: record between the watermark and the read is above no floor the walk starts from, and
    #: the map does not reflect it either. A mailbox `historyId` read before the first
    #: `threads.get` cannot be too high for any thread that response then fetched, because
    #: every change to those threads after their reads carries an id above it. A watermark
    #: read *after* the fetches can be too high, and `max(thread_history_ids)` - the
    #: arithmetic re-derivation a reviewer proposed in this field's place - is exactly such
    #: a value.
    #: `test_a_watermark_taken_after_the_fetch_can_hide_a_change_the_handle_should_see`
    #: executes that, so this comment is not the evidence for it.
    #:
    #: **Nothing arithmetic cross-checks it, and pretending otherwise would be the wider
    #: claim.** No relation to `thread_history_ids` holds in general: a quiet thread's own
    #: id is below this one, and a thread changed between the observation and its read has
    #: one above it. So this field is observed-and-signed, exactly like `fetched_at`,
    #: `mapping_digest` and `account_hash`, none of which is re-derived either. The
    #: signature is what makes it not-a-second-claim; a forged watermark needs a forged
    #: signature.
    history_id: str = Field(min_length=1, max_length=MAX_GMAIL_NUMERIC_ID_DIGITS)
    mapping_digest: str = Field(min_length=1, max_length=64)
    ttl: int = Field(ge=MIN_HANDLE_TTL_SECONDS, le=86_400)
    #: The width each named thread's map was paged at when this handle was minted
    #: (`disclosure.pages.page_size`), positionally aligned with `thread_ids`. A `thread`
    #: continuation names `thread_map(map_id, page)`, and page *k*'s positions are
    #: `k * width` onward: the digest verifies that the thread's messages and order are the
    #: ones the handle was minted over, and this verifies that the *paging* is - a server
    #: whose measure constants changed under an outstanding handle would otherwise serve
    #: page *k* from a different starting position with no refusal (the independent review
    #: of 2026-09-15). Signed like everything else here.
    page_sizes: tuple[HandlePageSize, ...] = Field(min_length=1, max_length=MAX_HANDLE_THREADS)

    @model_validator(mode="after")
    def _the_threads_and_their_history_ids_line_up(self) -> HandlePayload:
        """Two positionally aligned tuples are one mapping, and one of them can be short.

        Checked here rather than where it is read, because this document is caller-supplied:
        a payload naming three threads and two `historyId`s would otherwise be read with a
        floor missing, and a missing floor is a thread the liveness probe silently does not
        cover. That is the shape of every finding in this project's ledger.
        """
        if len(self.thread_ids) != len(self.thread_history_ids):
            raise ValueError(
                f"a map_id names {len(self.thread_ids)} threads and "
                f"{len(self.thread_history_ids)} historyIds; they are one mapping written as "
                "two tuples and a thread without its own historyId is a thread the liveness "
                "probe cannot floor"
            )
        if len(self.thread_ids) != len(self.page_sizes):
            raise ValueError(
                f"a map_id names {len(self.thread_ids)} threads and {len(self.page_sizes)} "
                "page widths; a thread without the width it was paged at is a thread whose "
                "page k cannot be checked against this handle"
            )
        if len(set(self.thread_ids)) != len(self.thread_ids):
            raise ValueError("a map_id names one thread twice; it names a set of threads")
        for value in (self.history_id, *self.thread_history_ids):
            if GMAIL_NUMERIC_ID_RE.match(value) is None:
                raise ValueError(
                    "a historyId on this handle is not the shape Gmail returns: an unsigned "
                    f"64-bit integer of at most {MAX_GMAIL_NUMERIC_ID_DIGITS} ASCII decimal "
                    "digits. The value is not quoted (R-SEC-032)"
                )
        return self

    @property
    def history_id_at_fetch(self) -> dict[str, str]:
        """`{thread id: its own historyId at fetch}` - the LRU key's other half."""
        return dict(zip(self.thread_ids, self.thread_history_ids, strict=True))

    @property
    def page_size_at_mint(self) -> dict[str, int]:
        """`{thread id: the width its map was paged at when this handle was minted}`."""
        return dict(zip(self.thread_ids, self.page_sizes, strict=True))

    @property
    def expires_at(self) -> datetime:
        """`fetched_at + ttl`, and `fetched_at` is the moment the maps were **read**.

        Expiry is measured from the observation, never from the mint or from a later
        service. A handle whose age restarted whenever it was used is a handle that cannot
        expire, which is the same defect as restamping `fetched_at` on a cache hit and is
        the reason both are stated in one place (AD A.10).
        """
        return parse_instant("fetched_at", self.fetched_at) + timedelta(seconds=self.ttl)


def re_derivation_of(payload: HandlePayload) -> Affordance:
    """AD D.11's "the re-derivation call" for a handle whose payload has been **verified**.

    Only ever built from a verified payload. The two classes decided before the signature is
    checked - `handle_invalid` and `handle_key_rotated` - carry no affordance and say so:
    filling `args` from an unverified document would put caller-supplied strings into a
    connector-voiced field, which is the route R-SEC-030/032 closed on the disclosure side.

    **It is the call the parser accepts** (2026-09-15). It used to name `thread_ids`, an
    argument `mailweave_thread_map` does not take, so the one affordance every `handle_*`
    refusal offered was refused as an unknown argument when a client copied it - found when
    a `thread` continuation was made to carry its handle and the refusal became the restart
    of a traversal. Every handle this server mints names one thread
    (`HandleMinter.for_one_thread`), and that thread's map is page 0 of the re-derivation.
    A payload naming several threads - a shape `mint` admits and nothing ships - names its
    first; the map tool takes one thread.
    """
    return Affordance(
        tool=ToolName.THREAD_MAP,
        args={"thread_id": payload.thread_ids[0]},
    )


#: The stand-in width of the one unbounded integer a payload carries, `key_epoch`, for
#: `widest_handle_chars`: 64-bit decimal width, which no rotation counter reaches.
_WIDEST_INT_DIGITS: Final[int] = len(str(2**64 - 1))


def widest_handle_chars(thread_id: str) -> int:
    """The longest `map_id` this server can mint over one thread, in characters.

    A `thread` continuation carries its response's handle (navigation redesign, continuation
    correctness, 2026-09-15), so the width of a thread's pages has to charge for one - and it
    has to charge the same amount on every response over the thread, or the width would move
    with the digits of a `historyId`, the microseconds of a `fetched_at` or the epoch of a
    rotated key, and page *k* under one handle would not be page *k* under the next. So the
    probe charges every field at the bound the payload's own schema declares (a 128-character
    account hash, 64-character `fetched_at` and digest, `historyId`s at Gmail's widest, the
    ttl at its ceiling) and the unbounded epoch at 64-bit width, over exactly the encoding
    `mint` writes and the signature it appends. A function of the thread id alone.
    """
    body = json.dumps(
        {
            "v": HANDLE_VERSION,
            "key_epoch": 10**_WIDEST_INT_DIGITS - 1,
            "account_hash": "x" * 128,
            "thread_ids": [thread_id],
            "thread_history_ids": ["9" * MAX_GMAIL_NUMERIC_ID_DIGITS],
            "fetched_at": "x" * 64,
            "history_id": "9" * MAX_GMAIL_NUMERIC_ID_DIGITS,
            "mapping_digest": "x" * 64,
            "page_sizes": [2**64 - 1],
            "ttl": 86_400,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    signature = _b64url_encode(bytes(sha256().digest_size))
    return len(_b64url_encode(body)) + len(_SEPARATOR) + len(signature)


def _refuse(code: ErrorCode, message: str, affordance: Affordance | None = None) -> HandleRefused:
    return HandleRefused(code=code, message=message, affordance=affordance)


def mint(
    key: HandleKey,
    *,
    account_hash: str,
    history_id_at_fetch: Mapping[str, str],
    mailbox_history_id: str,
    fetched_at: str,
    mapping_digest: str,
    page_sizes: Mapping[str, int],
    ttl_seconds: int = HANDLE_TTL_SECONDS,
) -> str:
    """A signed `map_id` over one response's maps.

    `history_id_at_fetch` is `{thread id: that thread's own historyId}`, which is both halves
    of what a stateless redemption needs: the set of threads the handle names, and the LRU
    key A.10 specifies. Threads are stored **sorted**, because the handle names a *set*: two
    mints over the same maps are one string, so a caller cannot tell them apart and a digest
    over the same threads in a different fetch order is the same digest. `page_sizes` is
    `{thread id: the width its map is paged at}` over the same keys (`HandlePayload.page_sizes`).

    `fetched_at` is the stamp of the observation those maps came out of and is passed in
    rather than read from a clock here - one time is one fact, and the clock has already been
    read once by the `threads.get` that produced them. The handle's whole age is measured
    from it and it is never rewritten, here or anywhere below.

    `mailbox_history_id` is the **mailbox** watermark, and amendment A10 requires it to have
    been observed **before** this response read any of the threads named above. That
    ordering is the whole of its correctness and it cannot be checked here: this function
    sees two numbers and no clock, and a `historyId` carries no timestamp. It is checked
    where it is observable - `assemble` reads it before its first `threads.get`, and
    `test_the_mailbox_watermark_is_observed_before_the_first_thread_is_fetched` executes
    that ordering against the call log rather than against this sentence.

    It replaces `min(thread_history_ids)`, which was derived here so that it could not be a
    second, disagreeing claim (R-ARCH-031). The derivation is gone and the reason it existed
    is not: a watermark is now observed like `fetched_at` and `mapping_digest` beside it,
    and like both of those it is protected by the signature rather than by arithmetic. What
    was bought with the derivation - see `HandlePayload.history_id` - was an unbounded walk,
    and R-RETR-060 measured what that costs.
    """
    parse_instant("fetched_at", fetched_at)
    if not history_id_at_fetch:
        raise ValueError("a map_id names at least one thread")
    for value in history_id_at_fetch.values():
        if GMAIL_NUMERIC_ID_RE.match(value) is None:
            raise ValueError(
                "a historyId is not the shape Gmail returns; the value is not quoted (R-SEC-032)"
            )
    if GMAIL_NUMERIC_ID_RE.match(mailbox_history_id) is None:
        raise ValueError(
            "a mailbox watermark is not the shape Gmail returns; the value is not quoted "
            "(R-SEC-032)"
        )
    if set(page_sizes) != set(history_id_at_fetch):
        raise ValueError("a map_id carries a page width for exactly the threads it names")
    threads = tuple(sorted(history_id_at_fetch))
    per_thread = tuple(history_id_at_fetch[thread_id] for thread_id in threads)
    payload = HandlePayload(
        v=HANDLE_VERSION,
        key_epoch=key.epoch,
        account_hash=account_hash,
        thread_ids=threads,
        thread_history_ids=per_thread,
        fetched_at=fetched_at,
        history_id=mailbox_history_id,
        mapping_digest=mapping_digest,
        page_sizes=tuple(page_sizes[thread_id] for thread_id in threads),
        ttl=ttl_seconds,
    )
    body = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    encoded = _b64url_encode(body)
    signature = hmac.new(key.material, encoded.encode("ascii"), sha256).digest()
    return f"{encoded}{_SEPARATOR}{_b64url_encode(signature)}"


@dataclass(frozen=True)
class HandleMinter:
    """What `assemble` needs in order to put a `map_id` on a source, and nothing more.

    Passed in rather than constructed there, and **optional**: a run with no minter produces
    sources whose `map_id` is `None`, which is what every response before WS-06 carried and
    is the honest value for a server that has no key. Threading the key through the retrieval
    layer as an argument keeps `assemble` free of the token store, and keeps "this server can
    mint handles" a fact about how it was called rather than about a global.
    """

    key: HandleKey
    account_hash: str
    ttl_seconds: int = HANDLE_TTL_SECONDS

    def for_one_thread(
        self,
        *,
        thread_id: str,
        history_id: str,
        mailbox_history_id: str,
        fetched_at: str,
        digest: str,
        page_size: int,
    ) -> str:
        """A handle over one source's thread. `Source.map_id`'s value.

        `mailbox_history_id` is per **response**, not per thread, and is threaded through
        every call rather than stored on this object for the reason the object exists: a
        `HandleMinter` says "this server can mint handles", which is a fact about how it was
        constructed, while the watermark is a fact about one response's reads and has to be
        observed again for the next one. A minter carrying a watermark would be a minter
        that could mint a handle over a watermark taken before some other response's fetch,
        which is the one ordering amendment A10 forbids.
        """
        return mint(
            self.key,
            account_hash=self.account_hash,
            history_id_at_fetch={thread_id: history_id},
            mailbox_history_id=mailbox_history_id,
            fetched_at=fetched_at,
            mapping_digest=digest,
            page_sizes={thread_id: page_size},
            ttl_seconds=self.ttl_seconds,
        )


def _decode_payload(map_id: str) -> tuple[str, str, HandlePayload]:
    """`(encoded payload, encoded signature, the parsed payload)`, or `handle_invalid`.

    Nothing in the returned payload has been *verified* at this point. It is parsed only, so
    that `key_epoch` can be read (see the module docstring, step 2) and so that a malformed
    handle is refused with a class that says so.
    """
    if not map_id or len(map_id) > MAX_HANDLE_CHARS:
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            "a map_id is a bounded base64url payload and signature; this one is empty or "
            f"longer than {MAX_HANDLE_CHARS} characters. Its content is not reproduced here",
        )
    encoded, separator, signature = map_id.partition(_SEPARATOR)
    if not separator or not encoded or not signature:
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            "a map_id is two base64url segments separated by a dot; this one is not. Its "
            "content is not reproduced here: it is caller-supplied text and an error that "
            "quotes what it refused echoes whatever was sent (AD A.11)",
        )
    try:
        raw = _b64url_decode(encoded)
        document: Any = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, ValueError) as failure:
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            "a map_id's payload segment is not base64url of a JSON document. Its content is "
            "not reproduced here",
        ) from failure
    if not isinstance(document, dict):
        raise _refuse(ErrorCode.HANDLE_INVALID, "a map_id's payload is not a JSON object")
    try:
        payload = HandlePayload.model_validate(document)
    except ValidationError as failure:
        summary = failure_summary(HandlePayload, failure)
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            f"a map_id's payload does not have the documented shape: {summary}. Values are "
            "omitted from this message on purpose - the document is caller-supplied",
        ) from failure
    if payload.v != HANDLE_VERSION:
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            f"this map_id declares handle schema v{payload.v}; this server mints and reads "
            f"v{HANDLE_VERSION}. Re-derive the map to obtain a current handle",
        )
    return encoded, signature, payload


def verify(map_id: str, *, key: HandleKey, account_hash: str, now: datetime) -> HandlePayload:
    """AD A.10 step 1: HMAC, `key_epoch` and TTL. **No network, and no cache.**

    Raises `HandleRefused` carrying one of `handle_invalid`, `handle_key_rotated` or
    `handle_expired` - three distinct classes, each with a different cause and a different
    remedy. This function establishes exactly one thing: *this server minted this handle, for
    this mailbox, recently enough to be worth re-verifying.* It establishes **nothing about
    the mailbox**; that is step 2's job and step 2 is the one that can fail. A docstring here
    that said "the handle is valid" would be the over-claim this round is about.
    """
    encoded, signature, payload = _decode_payload(map_id)
    if payload.key_epoch != key.epoch:
        raise _refuse(
            ErrorCode.HANDLE_KEY_ROTATED,
            f"this map_id was signed under key epoch {payload.key_epoch} and this server "
            f"now signs under epoch {key.epoch}. The signing key was deliberately rotated, "
            "which is not the same as the handle having aged out: re-derive the map with "
            f"{ToolName.THREAD_MAP.value} to obtain a handle under the current epoch. No "
            "call is offered beside this refusal, because the epoch is read before the "
            "signature is checked and nothing in an unverified handle may fill one",
        )
    expected = hmac.new(key.material, encoded.encode("ascii"), sha256).digest()
    try:
        presented = _b64url_decode(signature)
    except (binascii.Error, ValueError) as failure:
        raise _refuse(
            ErrorCode.HANDLE_INVALID, "a map_id's signature segment is not base64url"
        ) from failure
    if not hmac.compare_digest(expected, presented):
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            "this map_id's signature does not verify under this server's handle key, so it "
            "was not minted here or it has been altered. Re-derive the map with "
            f"{ToolName.THREAD_MAP.value}. No call is offered beside this refusal: nothing "
            "in an unverified handle may fill a connector-voiced field",
        )
    if payload.account_hash != account_hash:
        raise _refuse(
            ErrorCode.HANDLE_INVALID,
            "this map_id was minted for a different account than the one this server is "
            "authorised for. The account is part of the signed payload, so this is a handle "
            "presented to the wrong mailbox rather than a handle that has gone wrong. "
            f"Re-derive the map with {ToolName.THREAD_MAP.value}",
        )
    if now.astimezone(UTC) >= payload.expires_at:
        raise _refuse(
            ErrorCode.HANDLE_EXPIRED,
            f"this map_id was minted over maps fetched at {payload.fetched_at} with a "
            f"{payload.ttl}s ttl and that window has passed. Expiry is measured from the "
            "fetch and is never restamped, so a handle in daily use ages exactly as fast as "
            "the observation behind it. Re-derive the map",
            re_derivation_of(payload),
        )
    return payload
