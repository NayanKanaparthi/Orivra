"""Compile-time constants.

Every value here is traceable to a governing document. Values the rubric marks
``[UNSET - register at G0]`` are **absent from this module on purpose**: giving them a
default here would make the default the de facto bar (WORK_ORDER "Binding constraints").
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final

# --- OAuth scopes (AD A.4, RR SEC-01) --------------------------------------------------
# The server holds exactly one Gmail scope. The harness' destructive scope lives in the
# harness package and must never appear in server code (RR SEC-03); the scope-literal
# CI sweep enforces that.
READ_SCOPE: Final[str] = "https://www.googleapis.com/auth/gmail.readonly"
SERVER_SCOPES: Final[tuple[str, ...]] = (READ_SCOPE,)

# --- Runtime egress allowlist (AD D.8, RR SEC-07) --------------------------------------
# Exactly two runtime hosts. The model host is reachable only from `mailweave
# setup-models`, which is not part of the server process.
GMAIL_API_HOST: Final[str] = "gmail.googleapis.com"
OAUTH_TOKEN_HOST: Final[str] = "oauth2.googleapis.com"
RUNTIME_EGRESS_ALLOWLIST: Final[frozenset[str]] = frozenset({GMAIL_API_HOST, OAUTH_TOKEN_HOST})

# --- Setup-time egress (AD D.8, ADV-210) -----------------------------------------------
# The model host is reachable from exactly one code path, `mailweave setup-models`, and
# never from the server process or a query path. It is a **separate** allowlist rather than
# two more entries on the runtime one, because the property PF-5 verifies is that a cold
# server start with this host blocked completes: an allowlist that held it at runtime could
# not fail that test even if a hidden revalidation call existed.
MODEL_HOST: Final[str] = "huggingface.co"
#: Large files are served by redirect from a content host, and which one depends on the
#: caller's region. `us.aws.cdn.hf.co` is the one the owner's first pin attempt actually hit;
#: enumerating only that would move the failure to the next person in another region, so the
#: **suffix** is allowed rather than a guessed list of regional spellings.
#:
#: Exact hosts and a suffix are separate mechanisms on purpose. The runtime allowlist keeps
#: exactly-spelled hosts and no suffix at all, which is why `MODEL_CDN_SUFFIXES` is applied
#: only where `SETUP_EGRESS_ALLOWLIST` is: a suffix rule is weaker than an exact match, and
#: it does not get to weaken the pair the server itself runs against.
MODEL_CDN_HOST: Final[str] = "cdn-lfs.huggingface.co"
MODEL_CDN_HOST_ALT: Final[str] = "cdn-lfs-us-1.hf.co"
MODEL_CDN_SUFFIXES: Final[tuple[str, ...]] = (".cdn.hf.co", ".hf.co", ".huggingface.co")
SETUP_EGRESS_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {MODEL_HOST, MODEL_CDN_HOST, MODEL_CDN_HOST_ALT}
)

# --- Gmail REST surface (AD A.5) -------------------------------------------------------
# No endpoint may be called that is not on this table; the path-literal CI sweep enforces it.
GMAIL_ENDPOINTS: Final[tuple[str, ...]] = (
    "gmail/v1/users/{userId}/messages",
    "gmail/v1/users/{userId}/messages/{id}",
    "gmail/v1/users/{userId}/threads/{id}",
    "gmail/v1/users/{userId}/history",
    "gmail/v1/users/{userId}/profile",
    "gmail/v1/users/{userId}/messages/{messageId}/attachments/{id}",
)

# --- Hard product constants (AD D.8) ---------------------------------------------------
GENERATIVE_LLM_CALLS: Final[int] = 0  # hard, not configurable

# --- Content processing caps (AD D.4a) -------------------------------------------------
MIME_DEPTH_CAP: Final[int] = 12
MIME_PART_CAP: Final[int] = 64
CHARSET_LADDER: Final[tuple[str, ...]] = ("utf-8", "cp1252", "latin-1")

# --- Payload parse bounds (R-SEC-006, R-SEC-007) ---------------------------------------
# Defensive parse bounds in the same sense as the HTML ones above: no rubric criterion is
# measured against them and neither is an ``[UNSET - register at G0]`` value. They bound
# the work done *before* `MIME_PART_CAP`/`MIME_DEPTH_CAP` can engage, because those two
# cap the `walk`, and the walk runs after the whole payload tree has been built. R-SEC
# measured the gap: a 200,000-sibling payload cost 1.7s in `model_validate` and 4.5s in
# processing at ~420MB peak RSS before any cap applied.
#
# Both figures are derived from the processing caps rather than picked: a hundred times
# the number of parts the pipeline will ever consider, and ten times the depth it will
# ever descend. Anything inside them is refused by nothing new; anything outside them is
# already orders of magnitude past what could be disclosed, and is refused whole, with
# `ContentProcessingError`, rather than silently truncated.
#
# The depth factor is ten rather than a hundred because it has a ceiling above it as well
# as a floor below it: the recursive `Part` model hits Pydantic's own recursion guard at
# 255 levels of nesting on this interpreter (measured, and re-measured by
# `test_the_depth_bound_sits_below_the_interpreters_own_recursion_guard` so the two cannot
# drift apart). The bound has to stay below that number for the refusal to be this
# module's typed error rather than a foreign `pydantic.ValidationError` (R-SEC-007), and
# `MIME_DEPTH_CAP * 100` would have sat above it.
PAYLOAD_PART_CAP: Final[int] = MIME_PART_CAP * 100
PAYLOAD_DEPTH_CAP: Final[int] = MIME_DEPTH_CAP * 10

# --- HTML parse bounds (AD D.4a 5; R-SEC-002) ------------------------------------------
# These are *defensive parse bounds*, not product thresholds: no rubric criterion is
# measured against them and none is a ``[UNSET - register at G0]`` value. They exist
# because HTML-to-text cost grows quadratically with DOM nesting (measured on this repo:
# selectolax 0.31s at 10k nested tags, 1.21s at 20k, 4.73s at 40k) and because
# `lxml.html` silently discards everything below its own internal nesting limit. Markup
# nested deeper than `HTML_DEPTH_CAP` is flattened - its *text* is kept - and source
# longer than `HTML_SOURCE_CHAR_CAP` is truncated; both are declared as reductions with
# character counts, never applied silently. The depth figure sits far above real mail
# (deeply nested newsletter table layouts reach the low tens) and far below the level at
# which lxml starts dropping content.
HTML_DEPTH_CAP: Final[int] = 64
HTML_SOURCE_CHAR_CAP: Final[int] = 2_000_000

# --- Disclosure budgets (AD D.4 table) -------------------------------------------------
BODY_CLEAN_SOFT_CAP_TOKENS: Final[int] = 600
BODY_CLEAN_HEAD_TRUNCATED_TOKENS: Final[int] = 250
#: D.4's `body_full` row. The escape hatch is a soft cap, not an exemption: a `body_full`
#: row is measured and degraded by the same A.9a ladder as every other row, and the hard
#: per-response ceiling below still binds. Read from the published table rather than
#: chosen here, for the reason every other figure in this block is.
BODY_FULL_SOFT_CAP_TOKENS: Final[int] = 4_000
#: The longest `q` this server will build a Gmail request out of. **Derived, not chosen:**
#: Gmail's documented `messages.list` request is a URL, `httpx` refuses a URL component past
#: 64 KiB, and a query is percent-encoded on the way there - so 8,000 characters is the
#: largest input that cannot reach that refusal however it encodes. Round 25 added it because
#: a 100,000-character query reached an **unwrapped** `httpx.InvalidURL` (which is not an
#: `httpx.HTTPError` and so escaped the Gmail layer's own "no bare exception crosses this
#: layer" invariant), and a 1,000,000-character one was echoed back about four times over in
#: a 4 MB response under a 9,000-token declaration (R-MCP-013).
MAX_QUERY_CHARS: Final[int] = 8_000

NORMAL_CEILING_TOKENS: Final[int] = 9_000
FLOOR_OVERFLOW_CEILING_TOKENS: Final[int] = 12_000

#: **The host's own cap on a rendered `CallToolResult`, in characters** (AD F PF-6,
#: `[VERIFIED]`). Published here beside the two token ceilings because it is a ceiling of the
#: same kind measured in a different unit, and because until round 26 no character measure
#: existed anywhere in `server/src` at all: `grep -rl maxResultSizeChars server/src` returned
#: nothing, so a twelve-message thread went over this figure declaring `truncated_by: null`,
#: `partial: false` and `included: 12 of 12` (R-DISC-033, R-MCP-020/021).
#:
#: **Why the server has to hold the number itself.** The host cuts an over-cap result *above*
#: the SDK: driving the identical call in-process and through the real `Client` returns
#: byte-identical sizes, so nothing between this renderer and the client reduces anything, and
#: nothing downstream can add the marker afterwards. The one channel by which a host could
#: state its own cap - `_meta["anthropic/maxResultSizeChars"]` on the request - is not read by
#: this build; reading it and preferring it to this figure is the principled version and is
#: PF-6's, not this round's. Until then the constant is the [VERIFIED] figure the architecture
#: publishes, and it is enforced rather than assumed.
HOST_RESULT_CHAR_CAP: Final[int] = 25_000

# --- Retrieval caps referenced by withheld records (AD A.7) ----------------------------
#
# The whole of A.7's "Global caps per top-level query" table, enforced by
# `mailweave.policy.budget` (WS-10). They are constants rather than settings for the reason
# the module docstring gives, and every one of them is here rather than at its use site so
# that `test_every_published_cap_is_a_constant_this_module_enforces` can sweep the table
# against the code instead of against a reader's memory.
FLOOR_QUOTA_UNITS: Final[int] = 845
#: A.7's derived worst case: L0 105 + L1 205 + hit maps 480 + L1b 15 + L2 30 + L3 10 + LR
#: 162 + L4 160 = 1,167 u, rounded up to the published figure.
MAX_QUOTA_UNITS: Final[int] = 1_200
#: The same arithmetic plus L5's 1,010 u = 2,177 u, rounded up. Reached only when the
#: policy escalates to the semantic rung, never by a caller's request.
MAX_QUOTA_UNITS_SEMANTIC: Final[int] = 2_400
#: ADV-106: the quantity the old `max_gmail_calls = 40` was trying to bound. 40 was
#: arithmetically impossible against the rung caps.
MAX_API_CALLS: Final[int] = 80
#: Proxy-observable, which is the point: OBS-04 binds against this one because it is the
#: only one of the three an external witness can count (A.5b).
MAX_HTTP_REQUESTS: Final[int] = 24
#: RTT-bound, L0-L4.
#: **There is no minimum size for a withheld group** (round 29, corrected in the same round).
#: The first build of round 29 wrote a thread-granular withholding of one message as a record,
#: on the reasoning that a group standing for one message costs more than naming it. That was
#: read off the sizing constants, not the wire: on the real serializer a group of one renders
#: 451 characters and a record 461 (R-V01-007). So every withholding whose remedy is a thread
#: map is a group, whatever its size, and the special case is gone from the ledger, the ladder
#: and the assembly alike. The correction is recorded here because the wrong rule lived here.

#: The most message ids a **retry** the recovery chain mints may name (round 29, R-V01-010).
#: Not a cap on what a caller may ask for: a collapsed run's own expansion affordance names
#: every member of the run, hundreds for a long thread, and a request cap would have made a
#: call this server itself mints invalid at the tool that minted it - R-MCP-025's exact
#: defect, which the suite caught within the hour. The chain instead cuts a list that does
#: not fit to at most this many on its first hop and halves from there, so its length is
#: bounded whatever the caller named: one `view` hop, one cut, then `halvings_to_one(50)`.
MAX_MESSAGE_IDS_PER_RETRY: Final[int] = 50

#: How many `withheld_groups[]` entries a response names one by one before the rest are
#: folded into one `withheld_tail[]` entry per cap (round 29, R-V01-007). Forty-five
#: single-message threads capped away at `max_hit_threads: 1` are forty-four groups of ~500
#: characters - 22,000 against a 25,000-character cap, with no mail yet - and every one of
#: them says "thread capped, map it". Naming the first twenty-four and counting the rest is
#: round 27's third route out ("summarise the tail"), and it is what the ledger already
#: guarantees the counts of: every folded id is still in `withheld_ids`, the tail's count is
#: the exact size of that set, and it carries a call that widens the cap that folded it.
MAX_WITHHELD_GROUPS_NAMED: Final[int] = 24

#: The per-query wall-clock deadline for the lexical rungs L0-L4 (AD A.7).
#:
#: **7,700 ms since 2026-09-09. Owner-selected operational default, not a passed automatic
#: validation.** That distinction is load-bearing and is repeated wherever this number is
#: documented.
#:
#: **What it was.** 2,000 ms, a [DESIGN] planning value never measured against a network.
#: R-RETR-065 raised that in round 28: the pair `max_http_requests = 24` with a 2,000 ms
#: deadline assumes 83 ms per request, and nothing had checked it. Deadline runs 1 and 2 could
#: not settle it, because every arm declined on the host character cap rather than on the
#: clock - R-MCP-033 - so the clock was never the thing being measured.
#:
#: **What forced the change.** With R-MCP-033 closed, live v0.1 acceptance test 5.1 failed
#: twice on the shipped 2,000 ms, on `632cfbc` and again on `b0420ce`: the exact acceptance
#: call served truthfully at ~8,700 characters with **zero sources and zero matched rows**,
#: spending its whole deadline on one `messages.list` and four or five `messages.get` calls
#: and never affording the single `threads.get` a source requires
#: (`docs/reviews/ROUND_30/ZERO_EVIDENCE_DIAGNOSIS.md`).
#:
#: **The evidence for 7,700.** Deadline run 3, three pre-registered queries x three arms x
#: three counterbalanced repeats, `validation-records/deadline-validation-run3.json`. On the
#: exact acceptance query: 2,000 ms returned zero evidence in all three repeats; 7,700 ms
#: returned the same non-empty `body_clean` evidence in all three; 7,700 never hit
#: `max_server_ms`; its acceptance-query wall times were ~5,105 / 6,041 / 6,352 ms. Across all
#: three registered queries the candidate served evidence in all nine repetitions. The
#: 12,300 ms upper bound demonstrated no benefit over 7,700.
#:
#: **The caveat, which is not optional.** Run 3's registered verdict is `adoptable: false`.
#: The 12,300 ms reference arm took two `upstream_rate_limited` (403) declines from Gmail
#: during the run, which broke `stable` and `no_asymmetric_decline` and left
#: `acceptance_query_informative` false. 7,700 is therefore adopted by **owner decision on
#: repeat observations**, and this constant may not be cited as a passed registered
#: validation. See `validation-records/DEADLINE_DECISION.md`.
#:
#: **What 7,700 does not fix.** PF-21's arithmetic objection stands. `max_http_requests = 24`
#: against this deadline assumes 320 ms per request; run 3 observed roughly 400, so
#: `preflight/probes/latency.py` still returns FAIL on `24 * p90 > MAX_SERVER_MS` and no
#: deadline below about 9.6 s would clear it. This is the figure that makes the documented v0.1
#: workflows return mail, not the figure that reconciles the published pair. Amendment A13.
MAX_SERVER_MS: Final[int] = 7_700
#: CPU-bound, L5-L6, and separate by design (RT addendum 5.3): one deadline over both would
#: either strangle one rung or hand the other slack it has no use for. The two clocks are
#: sequential and independent - `enter_semantic` resets the start and swaps the cap - so
#: nothing assumes an ordering between them, and none was broken when `MAX_SERVER_MS` rose
#: past this figure on 2026-09-09.
MAX_SEMANTIC_MS: Final[int] = 6_000
#: AD A.5c. A counter rather than a semaphore: this server is stdio-serial, and a semaphore
#: would imply a blocking wait it never performs.
MAX_CONCURRENT_QUERIES: Final[int] = 2
MAX_HIT_THREADS: Final[int] = 12
MAX_SOURCE_THREADS: Final[int] = 4
MAX_POOL_THREADS: Final[int] = 25
MAX_POOL_MESSAGES: Final[int] = 300
MAX_RERANK_PAIRS: Final[int] = 25  # also the declared shortlist size k (AD A.7a, H-5)
MAX_RECENCY_FETCH: Final[int] = 8

#: The longest `Authentication-Results` record a row discloses (INJ-05). The header has no
#: length limit, and the disclosure estimate has to charge every field it carries, so this is
#: what makes the field chargeable at all. A longer record is **not truncated** - this
#: response does not rewrite a record it did not write - the row states `oversize: true`, and
#: the caller reads the message directly.
MAX_AUTH_RECORD_CHARS: Final[int] = 512


def auth_record_fits(record: str) -> bool:
    """Whether an `Authentication-Results` record is inside `MAX_AUTH_RECORD_CHARS`.

    **The record is the header as the receiving server wrote it, never the fenced string a
    row carries.** One comparison for the producer that decides between disclosing and
    declaring oversize, for the model that refuses a record over the bound, and for the
    ladder and page width that charge the record - so the three cannot measure different
    things again. They did: the model measured the fenced text against the same 512, and a
    record of 467 to 512 characters was disclosed by the producer, charged by the estimate
    and refused by the model, which turned a served thread into an internal error. The
    fence's characters are charged separately (`envelope.measure.AUTH_RECORD_CHARS`).
    """
    return len(record) <= MAX_AUTH_RECORD_CHARS


# --- Gmail transport (AD A.5a) ---------------------------------------------------------
# Every one of these is written in AD A.5a. They are constants rather than settings for the
# reason the module docstring gives: a value that can be edited without a review is a value
# the review never sees.
#
# `DEFAULT_PAGE_SIZE` is Gmail's own default and is set **explicitly** rather than
# defaulted, so `scan_scope.page_size` reports a number the call actually carried (GMAIL-04,
# RO F1). `MAX_PAGES_PER_QUERY` is the architecture's page budget: one page, with the
# residue declared as `more_pages` plus a widening affordance, never a silent stop.
DEFAULT_PAGE_SIZE: Final[int] = 100
MAX_PAGES_PER_QUERY: Final[int] = 1

# The page budget of a handle's **liveness walk** (AD A.10 step 2), which is a different
# kind of page from `MAX_PAGES_PER_QUERY`'s and so is its own number rather than that one
# reused (R-RETR-060). `MAX_PAGES_PER_QUERY` bounds a *disclosure* read: its residue is the
# ids on pages nobody fetched, declared as `more_pages` with a widening affordance. This
# one bounds a *sync* read whose length is a function of how much the mailbox has moved
# since the handle's watermark, and its residue is declared as `pages_exhausted` -> either
# `handle_stale` when the walk already saw a change, or `handle_stale_unverifiable` with
# the re-derivation affordance when it saw nothing (amendment A10).
#
# The value is 1 because amendment A10 made the walk start at the **mailbox** watermark
# observed before the fetch, so the window it covers is at most one handle ttl wide rather
# than "however long ago this thread last moved". One page of Gmail's own 100-record
# default therefore covers 100 mailbox changes inside 900 s. It was the same 1 before A10
# and it was not the same bound: it was `MAX_PAGES_PER_QUERY` restated as a literal over an
# unbounded window, which made `handle_stale_unverifiable` the routine answer.
MAX_LIVENESS_PAGES: Final[int] = 1

# Retrier (AD A.5a). Every HTTP attempt is charged to the accountant, including the attempt
# that 429'd, because the upstream quota was spent on it.
RETRY_BASE_MS: Final[int] = 250
RETRY_FACTOR: Final[int] = 2
RETRY_JITTER_FRACTION: Final[float] = 0.25
MAX_RETRIES: Final[int] = 3
MAX_BACKOFF_TOTAL_MS: Final[int] = 1_500

# Batcher (AD A.5a): a hard limit of 100, with >50 not recommended ([VERIFIED] RO F5). It is
# declared here and **not implemented in this round** - see the round-11 handoff. A batch of
# n costs n quota units and changes `http_requests` only.
MAX_BATCH_SUB_REQUESTS: Final[int] = 50

# --- Filesystem posture (AD A.4, RR SEC-04) --------------------------------------------
TOKEN_DIR_MODE: Final[int] = 0o700
TOKEN_FILE_MODE: Final[int] = 0o600
SALT_BYTES: Final[int] = 32

# --- Gmail numeric id shape (R-SEC-030 round 9, R-SEC-032 round 10) --------------------
# Gmail's `historyId` is an unsigned 64-bit integer rendered in decimal and `internalDate`
# is milliseconds since the epoch rendered the same way, so 20 digits is the widest either
# can be. Not a threshold anybody picked: it is the decimal width of a uint64.
#
# **This lives here, in the one module both layers can import, because the same field name
# has now been found unchecked at two different layers.** Round 9 gave the *seal*'s
# `history_id` a shape check written inline in `envelope/disposition.py`; round 10 found
# `envelope/reasons.py`'s `HistoryAddition.history_id` - the same field name, one layer up,
# with no seal in between - putting a whole English sentence on the disclosed JSON wire.
# Two independently written copies of one shape are how the second layer got missed, so
# there is one copy and both layers import it.
#
# `\A`/`\Z` rather than `^`/`$` deliberately: Python's `$` also matches immediately before
# a trailing newline, so `"123\n"` satisfies `^[0-9]{1,20}$`. In the seal that quirk is
# pre-filtered by `_sealed_scalar` running first; a check that depends on its caller's
# ordering is one the next caller gets wrong, which is exactly how this field reached the
# wire twice.
# --- Shapes shared across layers (R-ARCH-031, round 11's standing check) ---------------
# `is_one_line` lives here for the same reason `GMAIL_NUMERIC_ID_RE` does, one paragraph
# down: three layers were checking one shape and two of them had written the check out by
# hand. Round 10 found `envelope/reasons.py::_one_line` independently reimplementing
# `envelope/disposition.py::_is_one_line` **inside the diff that diagnosed the pattern**
# (R-ARCH-031, LOW, carried). Round 11's preflight record writer needed the same predicate a
# third time - in the *harness* package, where the private helpers of `envelope/` are not
# reachable at all - which is how a fourth hand-written copy gets written.
#
# So there is one, and every layer imports it. What it is not: a claim that a single-line
# string is safe. It is the floor. A field with a known shape gets that shape checked too.


def is_one_line(value: str) -> bool:
    """Whether `value` is a single line, by **Python's own** definition of a line break.

    `str.splitlines()` rather than a scan for `\n` and `\r` (R-SEC-029): a hand-listed set
    of boundary characters is a snapshot of what somebody knew, and U+2028, U+2029, U+0085,
    U+000B and U+000C are absent from it - two of which JavaScript and HTML/CSS renderers do
    treat as breaks. Comparing against the singleton list rather than against its length also
    catches a *trailing* break, since `"one\n".splitlines()` is `["one"]`.
    """
    return value.splitlines() == [value]


#: The longest string this repository will treat as an email address. RFC 5321 s4.5.3.1
#: bounds a forward-path at 256 octets and a domain at 255; 320 is the conventional
#: local(64)+@+domain(255) ceiling. It is a **refusal** bound, never a truncation: an
#: over-long token is not an address and is dropped, rather than shortened into one.
MAX_ADDRESS_CHARS: Final[int] = 320

#: The bounds on the four **sender-chosen** attachment scalars (round 26, R-MCP-016). Refusal
#: bounds, never truncations, for `MAX_ADDRESS_CHARS`' reason, and here rather than beside the
#: model for the reason everything in this block is here: a shape checked at one layer and
#: forgotten at the next is how one shape gets validated and its peers trusted.
#:
#: Each figure is the documented ceiling for what it bounds rather than a guess: 255 is the
#: filename length every mainstream filesystem states; a MIME type is `type/subtype`, whose
#: halves RFC 6838 s4.2 bounds at 127 characters each; a Gmail `partId` is a dotted path of
#: small integers; an `attachmentId` is an opaque base64url handle whose length is Google's to
#: choose, so its bound is deliberately generous and no property here depends on the figure.
MAX_ATTACHMENT_FILENAME_CHARS: Final[int] = 255
MAX_MIME_TYPE_CHARS: Final[int] = 255
MAX_PART_ID_CHARS: Final[int] = 64
MAX_ATTACHMENT_ID_CHARS: Final[int] = 4_096


def is_an_address(value: str) -> bool:
    """Whether `value` has the shape of an addr-spec, rather than header text that parsed loosely.

    Here for the reason `is_one_line` is here, and the reason is the same finding three times
    over (R-ARCH-031): a shape checked at more than one layer must have exactly one
    implementation. `structure/participants.py` needs it to decide what
    `email.utils.getaddresses` handed back - that function returns `('', 'garbage')` for a
    header value that is really prose - and `envelope/wire.py` needs the identical check at
    the wire boundary, because an address is mail-derived text and a field named `address`
    must not become a route for a sentence (R-SEC-030/032).

    Four mechanical conditions, the same four every scalar this project keeps must pass:
    non-empty, bounded, one line, and the documented shape. Deliberately **not** an RFC 5322
    grammar: this is the floor that keeps prose out, not a claim that what passes is
    deliverable mail.
    """
    if not value or len(value) > MAX_ADDRESS_CHARS:
        return False
    if not is_one_line(value) or any(character.isspace() for character in value):
        return False
    local, separator, domain = value.partition("@")
    return bool(separator and local and domain and "@" not in domain and "." in domain)


#: A machine-readable status / reason / error slug from a remote API: an identifier, never a
#: sentence. Used for Google's `error.errors[].reason` and `error.status` (the Gmail client)
#: and for the OAuth `error` code (the consent flow) - two layers, one shape, and the second
#: one originally spelled it `str.isidentifier()`, which accepts Arabic and CJK identifiers
#: and would have admitted a good deal that Google never emits.
REMOTE_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,63}\Z")


def clean_slug(value: object) -> str | None:
    """`value` if it is a remote API slug, else `None`. Never raises, never returns prose."""
    if isinstance(value, str) and REMOTE_SLUG_RE.match(value) is not None:
        return value
    return None


MAX_GMAIL_NUMERIC_ID_DIGITS: Final[int] = 20
GMAIL_NUMERIC_ID_RE: Final[re.Pattern[str]] = re.compile(
    rf"\A[0-9]{{1,{MAX_GMAIL_NUMERIC_ID_DIGITS}}}\Z"
)


# --- Where a listing looks (R-SEC-051, round 12 part 6) --------------------------------
# `messages.list` has two independent ways of saying whether SPAM and TRASH are in scope:
# the `includeSpamTrash` request parameter, and an `in:` operator inside `q`. Nothing on
# Gmail's side makes them agree, so a call that widens one and not the other samples a
# mailbox neither setting describes.
#
# Round 12 made the pair a single value (`preflight/scope.MailboxScope`) and kept it that
# way with two AST sweeps. R-SEC-051 found four ordinary call shapes that evade both:
# omitting the flag beside `query=<scope>.query`, and spelling the operator with an
# f-string, a concatenation or `.format` - none of which is an `ast.Constant`. An AST sweep
# reads what is written; a request carries what was computed.
#
# So the vocabulary lives here, in the one module every layer already imports, and the
# client checks the **composed query** against the flag at the point the request parameters
# are built (`_fetch_list_page`). That catches every spelling, because by then there is no
# spelling left - only a string. The sweeps stay as the early failure at the line somebody
# writes the mistake.

#: `in:` operators that put SPAM or TRASH into a listing's scope. `in:inbox` and the rest of
#: Gmail's location operators are ordinary query text and are not this coupling.
#:
#: Named individually because the harness's `MailboxScope` composes its two query spellings
#: out of them rather than writing them again: `-in:spam -in:trash` is the negation of two of
#: these, and a second hand-typed copy of a vocabulary is the shape this repository keeps
#: finding (R-ARCH-031).
ANYWHERE_OPERATOR: Final[str] = "in:anywhere"
SPAM_OPERATOR: Final[str] = "in:spam"
TRASH_OPERATOR: Final[str] = "in:trash"

#: The character Gmail reads as "and not this". Written here rather than in the parser
#: because two layers need it for the same reason - the parser to decide what a
#: decomposition probe may ask for, and `carries_nothing_to_select_by` below to decide what
#: a probe may be at all - and a vocabulary spelled twice is how the two come to disagree
#: (R-ARCH-031, the same argument as `WIDENING_MAILBOX_OPERATORS` above).
NEGATION_PREFIX: Final[str] = "-"
WIDENING_MAILBOX_OPERATORS: Final[tuple[str, ...]] = (
    ANYWHERE_OPERATOR,
    SPAM_OPERATOR,
    TRASH_OPERATOR,
)


#: Gmail's grouping and separating punctuation, stripped from both ends of a token before it
#: is compared with the operator vocabulary. Only the ends: punctuation *inside* an operator
#: is a different token, and this is a comparison rather than a parser (R-SEC-058).
QUERY_GROUPING_PUNCTUATION: Final[str] = "(){}[],;"

#: The character Gmail reads as opening and closing a phrase. Written here beside the
#: negation prefix and the scope operators because `matchable_content_of` below has to know
#: it to say what a token asks Gmail to match, and a second hand-typed copy of a query
#: vocabulary is the shape this repository keeps finding (R-ARCH-031).
PHRASE_QUOTE: Final[str] = '"'

#: Unicode's own category for a **format character**: invisible, of no width, carrying no
#: glyph of its own. Asked of the runtime rather than transcribed, for the reason
#: `content/html_text.py` gives where it uses the same category (R-SEC-033): a hand-list of
#: zero-width code points was sixteen of the hundred and seventy the standard defines, so
#: the next one Unicode adds is covered here without a code change. A token spelled out of
#: nothing but these asks Gmail to match nothing, however many code points long it is.
FORMAT_CHARACTER_CATEGORY: Final[str] = "Cf"

#: Every Unicode general category whose members carry **no character content of their own**,
#: each with the reason it is here. `matchable_content_of` removes them all, and it removes
#: them by asking `unicodedata.category` rather than by holding a list of code points, so a
#: character the standard adds tomorrow is covered without a code change.
#:
#: Round 17 removed `Cf` alone and its docstring described that as "a structural question ...
#: what, once everything that is not content is removed, is left for Gmail to match?"
#: (R-RETR-029). One category is not that question: a lone combining acute, a variation
#: selector and a C0 control were all "content", so a token spelled out of them became a
#: `terms` constraint and L3 composed the widening operator beside it with
#: `includeSpamTrash=true` - R-RETR-017's own wire shape through a spelling the predicate
#: did not cover. The categories are named individually, with the reason, because a reader
#: has to be able to check each one against what it claims:
#:
#:   * `Cc` - C0/C1 controls. A tab or a NUL is not a thing to search for;
#:   * `Cf` - format characters: ZWSP, ZWNJ, the bidi marks, the Arabic letter mark;
#:   * `Cs`, `Co`, `Cn` - surrogates, private use and unassigned. Nothing standard renders,
#:     and nothing here can say what a private-use code point means;
#:   * `Zs`, `Zl`, `Zp` - space separators, including NBSP and the ideographic space;
#:   * `Mn`, `Me` - non-spacing and enclosing marks. A mark *attached to a base character* is
#:     content and survives, because its base survives; a mark standing alone attaches to
#:     nothing and renders nothing.
#:
#: **The residue is named rather than glossed, and it is one set.** Unicode's
#: `Default_Ignorable_Code_Point` property covers characters that render as nothing while
#: carrying an ordinary category - U+3164 HANGUL FILLER (NFKC-folds to U+1160, category
#: `Lo`) and U+115F are its reachable members here - and `unicodedata` exposes no property
#: API for it in this runtime, so it cannot be *derived* the way every category above is.
#: Transcribing the set would be the hand-list this predicate exists to avoid, so those
#: spellings remain content, are executed rather than silently dropped, and are recorded as
#: open (R-RETR-029 residue; **WS-10**, and R-GMAIL for whether Gmail matches them at all).
#: U+2800 BRAILLE PATTERN BLANK is deliberately *not* in the residue: it is category `So`
#: and is a meaningful character in braille text, so treating it as content is a reading
#: rather than a gap.
NON_MATCHING_CHARACTER_CATEGORIES: Final[frozenset[str]] = frozenset(
    {FORMAT_CHARACTER_CATEGORY, "Cc", "Cs", "Co", "Cn", "Zs", "Zl", "Zp", "Mn", "Me"}
)


def matchable_content_of(token: str) -> str:
    '''The text one `q` token asks Gmail to **match**, or `""` when it asks for nothing.

    **This is the predicate the round-16 fix needed and did not have** (R-RETR-017). Its two
    neighbours below judge a token by *how it is spelled* - is it one of three named
    operators, does it start with a minus - and that is how an empty quoted phrase walked
    through both: `""` is a non-empty string, is not a scope operator and is not a negation,
    so it passed every check, became a probeable constraint, and L3 composed `in:anywhere ""`
    with `includeSpamTrash=true` over a mailbox nobody had asked about. An empty phrase is
    syntactically a phrase and semantically nothing. So are `subject:` with no value,
    `subject:""`, `" "`, `"\\t"`, `"\\xa0"`, `""""` and a token spelled entirely out of
    zero-width characters.

    Enumerating those eight spellings would be the same mistake one layer down. This asks a
    structural question instead - *what, once everything that is not content is removed, is
    left for Gmail to match?* - so it holds for spellings nobody has written down, including
    the ones a future operator introduces: an operator's content is its **value**, and an
    operator added to `OperatorName` tomorrow either carries a value or carries nothing.

    Five steps, each removing something that is not content:

      * NFKC, so a fullwidth or compatibility spelling reduces to its ASCII form - the same
        normalisation `operator_token` applies, for the same reason;
      * Gmail's grouping punctuation off both ends, so `(in:anywhere)` reads as `in:anywhere`;
      * the negation prefix, because **polarity is not content**: `-cutover` names the word
        "cutover", and the question here is whether a token names anything at all. Whether a
        token that only *excludes* may be probed alone is a different question, asked by
        `carries_nothing_to_select_by`;
      * the operator name, when there is one. `name:value` is an operator only when `name` is
        **unquoted** - the same rule `query.operators.tokenise` applies, so a colon inside a
        quoted phrase is content here exactly as it is there (R-RETR-018) and
        `"9:30 standup"` reports `9:30 standup` rather than an empty value for an operator
        called `"9`;
      * the phrase quotes and every character in `NON_MATCHING_CHARACTER_CATEGORIES` - which
        is asked of the runtime, category by category, and is one category wider than the
        `Cf` this used to remove (R-RETR-029) - then whitespace collapse.

    What is left is the string Gmail would look for. Empty means the token filters nothing,
    so a `q` made of such tokens is the empty `q` wearing quotes - which
    `Probe.__post_init__` already refuses under its own name. Executed by
    `test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled`.
    '''
    normalised = unicodedata.normalize("NFKC", token).strip(QUERY_GROUPING_PUNCTUATION)
    body = normalised[1:] if normalised.startswith(NEGATION_PREFIX) else normalised
    head, separator, tail = body.partition(":")
    value = tail if (separator and head and not head.startswith(PHRASE_QUOTE)) else body
    content = "".join(
        character
        for character in value
        if character != PHRASE_QUOTE
        and unicodedata.category(character) not in NON_MATCHING_CHARACTER_CATEGORIES
    )
    return " ".join(content.split())


def query_tokens(query: str) -> list[str]:
    """One `q`, split into the tokens **Gmail** would read, keeping a quoted run together.

    Gmail separates operators by whitespace and quotes a value that contains whitespace, so
    `from:"Amy Smith"` and `"three word phrase"` are each **one** token. Every predicate
    below asks a question about a token - is it a region declaration, does it name anything
    to match, does it only say what to leave out - and `str.split` answers each of them for
    a *fragment* of a quoted token rather than for the token.

    **That is not a cosmetic difference; it is round 18's own instance of this repository's
    recurring defect.** `carries_nothing_to_select_by('-from:x')` was `True`, so a negated
    participant was correctly refused as a decomposition probe of its own - and
    `carries_nothing_to_select_by('-from:"Amy Smith"')` was `False`, because the whitespace
    split produced `-from:"Amy` and `Smith"` and the second piece carries no negation. So the
    same constraint, written with a value that happens to contain a space, became an L1b unit
    whose `q` asks Gmail for the whole mailbox minus one sender - R-RETR-006's shape, reached
    through the one spelling nobody checked. One tokenisation, read by every predicate, is
    what stops the family from disagreeing with itself about the same token.

    An unbalanced quote closes at end of input, exactly as `query.operators.tokenise`'s own
    splitter does - the two are the same function, written here because `constants` is the
    module the parser imports rather than the other way round.
    """
    tokens: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in query:
        if char == PHRASE_QUOTE:
            in_quotes = not in_quotes
            current.append(char)
            continue
        if char.isspace() and not in_quotes:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def carries_no_content(query: str) -> bool:
    """Whether every token of `q` names nothing to match, so the `q` filters nothing.

    The whole-`q` form of `matchable_content_of`, written like its two neighbours so the
    family reads as one rule. A query with no tokens at all is not this shape - it is the
    empty `q`, refused by its own rule with its own message.

    Tokenised by `query_tokens`, so a quoted phrase is one token here as it is for every
    other member of the family. `'" "'` is one token whose content is empty, which is the
    right answer for the same reason the whitespace split reached it by accident.
    """
    tokens = query_tokens(query)
    return bool(tokens) and not any(matchable_content_of(token) for token in tokens)


def operator_token(token: str) -> str:
    """One whitespace-delimited token, reduced to the operator it would be read as.

    NFKC first, then the grouping punctuation off both ends, then case-folded by the caller.
    NFKC is what maps the fullwidth spelling `ＩＮ：ＡＮＹＷＨＥＲＥ` onto `IN:ANYWHERE`; the
    strip is what makes `(in:anywhere)` and `in:anywhere,` the same token as `in:anywhere`.
    The leading quote of a phrase search is deliberately **not** stripped: `"in:anywhere"` is
    a phrase search rather than an operator, and reading it as one would be a false refusal.
    """
    return unicodedata.normalize("NFKC", token).strip(QUERY_GROUPING_PUNCTUATION).casefold()


def carriage_token(token: str) -> str:
    """One `q` token reduced to the form two `q`s must share to be carrying the same fragment.

    The comparison behind `query.analysis.constraints_carried_whole`, which is the one
    derivation of *"did this probe carry that constraint whole?"*. Four reductions, and each
    one is a spelling difference that does not change what Gmail is asked to match:

      * NFKC, so a fullwidth spelling and its ASCII form are the same fragment;
      * case, because Gmail's operators and its text matching are both case-insensitive;
      * **surrounding phrase quotes**, because quoting a token *narrows* what it matches and
        never widens it. A.8a branch E-c executes a structured identifier as a quoted
        single-token query, so `"PO-2026-0041"` carries the term `PO-2026-0041`: the row it
        admits satisfies that term and more. The asymmetry is preserved by the tokenisation
        rather than by a rule - a multi-word phrase is **one** token quoted and **several**
        unquoted, so an unquoted `q` never carries a phrase fragment.

    **Polarity is not reduced.** `-from:x` and `from:x` ask opposite questions, so a `q`
    carrying one does not carry the other; this is the one place in the token family where
    the negation prefix is load-bearing rather than noise.

    **Gmail's grouping punctuation is not stripped either, and that is the difference from
    `operator_token`.** Its neighbours strip it because `(in:anywhere)` is the same operator
    as `in:anywhere`; here it is exactly what must not be reduced, because A.7 L3's widening
    step composes `{from:x to:x}` - a *disjunction* that is strictly wider than the `from:x`
    the caller wrote. Stripping the brace would have read the group's first member as the
    constraint and reported a widened participant `enforced`, which is R-RETR-020's own
    over-claim arriving through the derivation written to prevent it. A constraint fragment
    never carries grouping punctuation of its own: `ParsedOperator.render` does not emit it,
    a phrase is quoted rather than grouped, and a term written with a bracket is classified
    `passthrough` before it can become a constraint.
    """
    normalised = unicodedata.normalize("NFKC", token).casefold()
    negated = normalised.startswith(NEGATION_PREFIX)
    body = normalised[1:] if negated else normalised
    if len(body) >= 2 and body.startswith(PHRASE_QUOTE) and body.endswith(PHRASE_QUOTE):
        body = body[1:-1]
    return f"{NEGATION_PREFIX if negated else ''}{body}"


def carries_nothing_but_mailbox_scope(query: str) -> bool:
    """Whether every token of `q` is one of the operators that **leaves the default mailbox**.

    Narrower than "a mailbox-scope operator", deliberately, and the first line says so since
    round 19's spelling-versus-data sweep: `in:inbox` is a scope operator too and a `q` of
    nothing but it is *not* refused here. The reason is who wrote the query. This predicate
    reads the caller's own `q` through `why_this_q_is_not_a_probe`, and a caller asking for
    their inbox has asked for a listing MailWeave has no business refusing; what it may not do
    is answer that request from spam and trash. A `q` composed by a *rung* out of a subset of
    the query's fragments is held to the wider rule instead
    (`query.analysis.carries_nothing_to_select_by`), which reads the operator registry and
    refuses a probe of nothing but `in:inbox` for the same reason it refuses this one.

    A scope operator says *where* to look; it is not something to look **for**. A `q` made
    only of them asks Gmail for the whole mailbox exactly as an empty `q` does, which is
    what `Probe.__post_init__` already refuses - so refusing that shape too is the same
    rule, not a new one (R-RETR-006: `BroadeningRung` walked around the empty-`q` refusal
    by composing a non-empty string out of nothing but the widening operator).

    Read against `WIDENING_MAILBOX_OPERATORS` rather than a spelling of its own, through
    the same `operator_token` normalisation `widens_beyond_the_default_mailbox` uses, so
    the fullwidth, capitalised and grouped spellings that defeated the coupling twice
    cannot defeat this one either. A query with no tokens at all is not this shape - it is
    the empty `q`, which is refused by its own rule with its own message.
    """
    tokens = [operator_token(token) for token in query_tokens(query)]
    return bool(tokens) and all(token in WIDENING_MAILBOX_OPERATORS for token in tokens)


#: Gmail's location operator, written as the prefix its values are read under. Every member
#: of `WIDENING_MAILBOX_OPERATORS` is a spelling of it, and `in:inbox`, `in:sent`,
#: `in:drafts`, `in:chats` and every location Gmail names later are the *narrowing*
#: spellings.
#:
#: **What this is no longer** (round 19, R-RETR-036): it is not the answer to "does this
#: fragment declare the search region?". That question is about what an *operator does*, it
#: is answered from `OperatorKind.REGION` in `query/operators.py`, and asking it of one
#: lexical prefix was the round-18 defect - a newly registered region-selecting operator was
#: dropped from every probe with 2,274 tests green. What is left here is the one job a prefix
#: really can do: `region_name` takes it back off `REGION_LABEL_BY_OPERATOR`'s keys, which is
#: how `in:spam` becomes the region name `spam` a row reports.
MAILBOX_LOCATION_PREFIX: Final[str] = "in:"

#: The regions a **default** listing leaves out, keyed by the `in:` operator that names each
#: one and valued by the label id Gmail states on a message that is in it.
#:
#: Two spellings of one region, written as one mapping so a region cannot be added to the
#: operator vocabulary and forgotten in the label vocabulary - the R-ARCH-031 shape this
#: module exists to prevent. The keys are exactly `WIDENING_MAILBOX_OPERATORS` minus
#: `ANYWHERE_OPERATOR`, which is checked by execution rather than by reading
#: (`test_the_region_label_vocabulary_is_the_widening_operator_vocabulary`): `in:anywhere`
#: names no region of its own, it names all of them.
#:
#: The label ids are **written**, not derived from the operator by upper-casing it. That
#: derivation happens to hold for these two and does not hold in general - Gmail's `in:drafts`
#: is the label `DRAFT` - and a rule that is right twice by luck is a claim about Gmail's
#: label vocabulary that nothing here can establish (R-GMAIL).
REGION_LABEL_BY_OPERATOR: Final[Mapping[str, str]] = MappingProxyType(
    {SPAM_OPERATOR: "SPAM", TRASH_OPERATOR: "TRASH"}
)


def region_name(operator: str) -> str:
    """The bare region a location operator names: `in:spam` and `-in:spam` both -> `spam`.

    Polarity is stripped for the reason `declares_the_search_region` gives: it decides
    *which* region a fragment declares, never whether it declares one.
    """
    normalised = operator_token(operator)
    body = normalised[1:] if normalised.startswith(NEGATION_PREFIX) else normalised
    return body.removeprefix(MAILBOX_LOCATION_PREFIX)


def mailbox_regions_of(label_ids: Iterable[str]) -> tuple[str, ...]:
    """Which regions **outside the default mailbox** these observed labels place a message in.

    The one derivation of a message's mailbox provenance (OD-5, A9-A1), and it reads the
    message's **own labels** - what Gmail stated about the message - rather than the query
    that found it. Deriving it from the query would be "a value accepted from the caller when
    the same value is already derivable from what was observed", which is the defect class
    this project has found more than a dozen times; the label set is what was actually
    observed, so it is what the row reports.

    Returned in the fixed order of `REGION_LABEL_BY_OPERATOR` rather than in the order Gmail
    listed the labels, so two observations of one message produce one answer. Empty means the
    observed labels place the message in neither region - which is a claim about the labels,
    not about whether any were observed; that second question is `MailboxProvenance.observed`
    and it is a different field for the reason `observed_internal_dates` is absent rather
    than zero for an id no observation placed.
    """
    stated = frozenset(label_ids)
    return tuple(
        region_name(operator)
        for operator, label in REGION_LABEL_BY_OPERATOR.items()
        if label in stated
    )


def is_the_widening_mailbox_operator(fragment: str) -> bool:
    """Whether this fragment is the operator `BroadeningRung` substitutes when it widens.

    A location a broadening *replaces* is a location it did not search, so the rung has to
    tell "the caller already asked for everywhere" - where the substitution is the identity
    and the constraint really was enforced - from "the caller asked for spam and we searched
    everywhere", where it was not. Normalised through `operator_token` like its neighbours,
    so the grouped, fullwidth and capitalised spellings answer the same.
    """
    return operator_token(fragment) == ANYWHERE_OPERATOR


def widens_beyond_the_default_mailbox(query: str) -> bool:
    """Whether `q` asks Gmail to look in SPAM or TRASH.

    Token-wise, so that `-in:spam` - which *narrows* - is not read as widening, and so that
    an operator inside a longer word (`in:spammers`) is not either. Gmail's query grammar
    separates operators by whitespace, and a value containing whitespace is quoted; a quoted
    `"in:anywhere"` is a phrase search rather than an operator, and reading it as one would
    be a false refusal, so the leading quote is left attached and simply fails to match.

    **Case-folded, because Gmail's operators are.** `IN:ANYWHERE` was a fifth evasion of the
    coupling, one the round-13 implementer found while checking whether the claim beside
    `WIDENING_MAILBOX_OPERATORS` - "that catches every spelling, because by then there is no
    spelling left, only a string" - was true of the code. It was not: the guard matched
    exactly, so a caller who typed the operator in capitals passed the pairing check and put
    a widened `q` on the wire with `includeSpamTrash=false`. Folding is strictly the
    conservative direction: it can only refuse a *disagreeing* pair that used to be allowed.

    **Normalised and stripped of grouping punctuation** (R-SEC-058). Case-folding closed one
    evasion and the docstring then described the remaining residue as "a different spelling of
    the same *intent* - `label:spam`". That was the wrong residue for the shapes that were
    still open: `(in:anywhere)`, `{in:anywhere in:spam}`, `in:anywhere,` and a fullwidth
    `ＩＮ：ＡＮＹＷＨＥＲＥ` are not a different intent, they are the **same operator** with
    punctuation or Unicode equivalence around it - the same class as the case evasion, because
    `str.split` tokenises on whitespace only. Each of them travelled beside
    `includeSpamTrash=false` without `_fetch_list_page` raising.

    So each token is NFKC-normalised - which is what folds fullwidth and compatibility forms
    onto their ASCII spellings - and stripped of Gmail's grouping and separating punctuation
    at both ends, before the fold and the comparison. Both steps can only make the guard
    refuse a *disagreeing* pair it used to allow, never the reverse, which is what makes them
    safe to apply without knowing Gmail's parser: a query that never widens cannot start
    widening because of a strip.

    What it is still not is a parser, and the residue is now named at the right width:

      * a **different intent** spelled another way - `label:spam`, `category:`, or something
        Gmail adds later - is not in the vocabulary and is not seen;
      * punctuation *inside* the operator rather than around it - a zero-width space between
        `in` and `:` - survives normalisation as a separate code point and is not seen. It is
        stripped from mail *content* by the invisible-character pass, not from a query;
      * whether Gmail itself reads any of these as the operator is a fact about Gmail's parser
        that nothing in this repository can settle. The guard is conservative if it does not
        and closed if it does, and PF-20 is where the live run answers it.
    """
    folded = frozenset(operator.casefold() for operator in WIDENING_MAILBOX_OPERATORS)
    return any(operator_token(token) in folded for token in query_tokens(query))


# --- Query analysis and the lexical ladder (AD A.6, A.6a, A.7, A.8a) -------------------
# Every value below is written in the architecture. They are constants rather than
# settings for the same reason the transport's are: a number that can be edited without a
# review is a number the review never sees.

#: AD A.6a rule 3. A *relative* date window is widened by this many days on each bounded
#: side, because Gmail's `after:`/`before:` are date-valued and their boundary zone is not
#: documented for this account. An explicit user-supplied absolute date is **not** widened.
#: PF-14 measures the real boundary behaviour; if it is deterministic this drops to 0.
DATE_MARGIN_DAYS: Final[int] = 1

#: AD A.7 cap table: `max_relax_probes = min(k_constraints, 6)`. The ceiling half.
MAX_RELAX_PROBES_CEILING: Final[int] = 6

#: AD A.7 cost table, L1b row: `<=3 x 5 u`. One `messages.list` per decomposed constraint.
MAX_DECOMPOSITION_PROBES: Final[int] = 3

#: AD A.7 cost table, L3 row: `<=2 x 5 u`.
MAX_BROADENING_PROBES: Final[int] = 2

#: AD A.7's L3 description, "dates x4": a broadened window is this multiple of the parsed one.
BROADENING_DATE_FACTOR: Final[int] = 4

#: AD A.7 cap table, `max_body_fetches`: 10 at L1, 5 at L0. Hits beyond the cap are
#: disclosed as stub rows at declared reduced depth - **not** withheld, not dropped.
MAX_BODY_FETCHES_L0: Final[int] = 5
MAX_BODY_FETCHES_L1: Final[int] = 10

#: AD A.8a branch E-b: a quoted phrase qualifies at three or more tokens after stopword
#: removal, and fires only at a hit count in [1, 3].
EXACT_PHRASE_MIN_TOKENS: Final[int] = 3
EXACT_PHRASE_MAX_HITS: Final[int] = 3

#: AD A.8a branch E-c: a structured identifier fires at a hit count in [1, 3].
EXACT_IDENTIFIER_MAX_HITS: Final[int] = 3

#: AD A.8a branch E-a: `rfc822msgid:` fires only at exactly one hit. Identity, not retrieval.
EXACT_MSGID_HITS: Final[int] = 1

#: AD D.3 rule 2: `hit_count in [1,5]` is one of the four conjuncts of the L1 stop.
L1_STOP_MAX_HITS: Final[int] = 5

#: AD A.8a branch E-c's shape half: "an invoice/order/ticket/PO/SKU-shaped token
#: (>=6 chars, >=2 digits, no dictionary hit)".
STRUCTURED_IDENTIFIER_MIN_CHARS: Final[int] = 6
STRUCTURED_IDENTIFIER_MIN_DIGITS: Final[int] = 2


def max_relax_probes(constraint_count: int, ceiling: int | None = None) -> int:
    """AD A.7: `max_relax_probes = min(k_constraints, 6)` (ADV-105).

    A function rather than a constant because the cap *scales with the parsed constraint
    count*, and writing it as a bare 6 is what made the previous table disagree with
    itself. Untried drops are reported through `empty_diagnosis.status`, which is why the
    cap can bind without hiding anything.

    `ceiling` is WS-15's `relax.max_probes` argument (round 24), and it **can only raise**:
    the published 6 is a floor on what a caller may ask for, not a value they may lower. A
    settable ceiling exists because `empty_diagnosis` has offered
    `{"relax": {"max_probes": k}}` since round 5 and no parameter behind it existed - an
    affordance naming an argument no code accepts, which contract R-07 forbids and which
    only became visible when WS-15 gave the arguments a schema to be checked against.
    """
    if constraint_count < 0:
        raise ValueError("a constraint count is not negative")
    bound = MAX_RELAX_PROBES_CEILING if ceiling is None else max(MAX_RELAX_PROBES_CEILING, ceiling)
    return min(constraint_count, bound)
