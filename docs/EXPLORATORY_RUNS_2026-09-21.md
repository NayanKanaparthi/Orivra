# Five Orivra-only exploratory runs, 2026-09-21

**Exploratory results. Not an evaluation, not a comparison, and not evidence of user value.**
The questions were assistant-authored, which `USER_TASK_PILOT.md` explicitly forbids for a
pilot, and the mailbox is the seeded synthetic corpus. Nothing here supports a claim about
behaviour on real correspondence.

**Content-free by construction.** No question text, message identifiers, subjects, sender
names or mail content appear in this file. The transcripts are held privately outside the
repository and are not committed.

## Assessment

**No run is a verified success.** Zero of the cited message identifiers were checked against
returned content, because the tool outputs were not preserved. Correctness and citation
support are unscored for all five.

| Run | Task shape | Assessment | Reason |
|---|---|---|---|
| 1 | all clauses addressed | **partial completion** | per-message attribution is body-derived (see below); citations unverified |
| 2 | all clauses addressed | **partial completion** | same |
| 3 | all clauses addressed | **partial completion** | self-narrowed the corpus scope and declared it; answers a smaller question than asked |
| 4 | all clauses addressed | **insufficient evidence** | ordering of the two threads rests on identifier ordering with no observed timestamps; the connection is declared inference |
| 5 | all clauses addressed | **partial completion** | same attribution problem; citations unverified |

## The finding that matters most

**`MessageRow` carries no sender field.** `envelope/wire.py:932` defines the disclosed row
with `headers_observed`, `reply_to_differs` and `authentication`, and no address for who sent
the message. Sender identity lives one level up in the thread-level participant index, which
is address-keyed with five disjoint role lists and **deliberately has no `display_name`
field**, because a display name is spoofable mail-derived text; what survives is a count and a
fenced list.

So per-message attribution is not available on the wire. Every "X said", "Y approved",
"Z decided" in all five answers was read out of message body text, which the response itself
fences as `trust: untrusted_third_party`. The runs presented those attributions as explicit
statements. One run noticed and said so; the others did not.

This is checkable from the source with no mailbox access, and it is the class of claim the
product's own threat model exists to contain.

## Timestamps

Partly available, and the runs' blanket "rows carry no timestamps" is unverified in both
directions. `Envelope` writes `internal_date` onto each row's wire form from the certificate's
`observed_internal_dates`, and `wire.py`'s own note says "a row whose id no observation placed
carries no `internal_date` on the wire". So presence is conditional on the observation that
produced the row. Whether these particular rows carried it needs the outputs.

## Two defects, confirmed in source

**D1. A decline that is neither retryable nor terminal.** `surface/server.py:203` catches every
typed `GmailFault` and calls `declined(...)` with no affordance, no narrowing and no
`terminal`, producing `retry_with: null` with `terminal: false`. `surface/recovery.py` states
the contract it breaks: "when no smaller legal request can return evidence, the decline carries
`retry_with: null` **and says so**". A caller cannot distinguish a final refusal from a refusal
that merely offers nothing, which is the stated purpose of the flag.

Two separable things were tangled in the observed incident and must not be fixed as one:

1. **Caller misuse.** A thread identifier was passed where a message identifier was required.
   Whether the server should probe for that is an open product question, not a conclusion.
   Automatic thread-identifier probing on every message 404 is **not** adopted here.
2. **Server behaviour.** Independently of any misuse, this refusal violated the recovery
   contract. That is the defect. It applies to every typed Gmail fault on this clause, not
   only to a 404.

Also on the wire: the appended in-band sentence runs into the preceding one with no separator.

**D2. `MAX_SERVER_MS` does not bound a call.** It reaches the Gmail layer as
`BackoffState.remaining_ms`, and `_budget_ms()` takes `min(max_backoff_total_ms, remaining_ms)`,
so it bounds **retry sleeps only** and never a request. With `timeout=30.0` on the httpx client
(`surface/runtime.py:119`), `MAX_RETRIES = 3` and a per-message fetch, a four-message read has a
worst case of 4 × 4 × 30s = 480 seconds plus at most 1.5 seconds of sleeps. `MAX_SERVER_MS =
7_700` constrains 1.5 of those 480.

The observed four-minute silence sits inside that envelope. **Whether that particular event was
host-side or server-side is undetermined** and the structural finding stands either way: no
timer enforces "degrade or refuse, never hang" on the read path.

## Why the logs could not settle it

**Per-call tracing is built, wired, and off.** `trace/sink.py` appends JSONL records under
`traces/personal/`, `surface/service.py:200` takes `trace_sink: TraceSink | None = None`, and
`surface/runtime.py` never constructs one. So the served path writes no per-call record, no
`traces/` directory exists, and the tool designed to surface it (`orivra_trace`) is declared
and deliberately unpublished.

**The server emits only a startup banner to stderr.** There is no request logging anywhere in
either source tree.

So server-side logging is **known incomplete**, and an absent entry in the desktop log proves
nothing about whether a request arrived. Host-side logging completeness is unknown here. The
desktop log folder is listed as connected to this session but every read of it was refused, so
it was not inspected.

## Contamination: possible, not established

Four of the five runs read the desktop memory store; one did not. Whether anything carried
between runs is **unknown**. It is recorded as a possible confound, not a demonstrated one.

Consequence either way: **cross-run agreement is not used as correctness evidence here**, and
was not. Three runs converging on the same identifiers would be meaningful only from
independent retrievals, and independence is exactly what is unestablished.

## Smallest missing artifact per gap

| Gap | Smallest artifact that closes it |
|---|---|
| Correctness and citation support | the structured content of the read results from each run, for the cited identifiers only |
| Run 4's ordering | the `internal_date` field on two rows |
| The timed-out call | one re-run with the trace sink enabled, or host-side logging shown to be complete |
| Contamination | the memory store's contents as of the run window |

Nothing in this file is a gate, and no code was changed to produce it.

---

## Bounded repair, same day

Four repairs, scoped to what the runs demonstrated. Nothing else moved: questions, mailbox,
environment and the acceptance campaign are as they were. Each repair is held by a regression
in `tests/test_repairs_2026_09_21.py` driven through `surface.server.call`, and each regression
was checked to fail with its repair reverted.

**1. The request deadline is enforced.** `gmail/retry.py::Deadline` is built once per tool
call from the service's clock and bound to the client (`GmailClient.bind_deadline`). Every
`_request` reads it live: an attempt is not started with under `MIN_ATTEMPT_MS` left, each
attempt's HTTP timeout is `min(30 s, remaining)`, and the backoff's sleep bound is refreshed
before every sleep. Reads bind `MAX_SERVER_MS`; a search binds `max_server_ms + max_semantic_ms`,
the sum the accountant already charges across. Overrun raises `GmailDeadlineExceeded`
(`budget_exhausted`), which declines with the same narrowing chain a size refusal gets. On a
real clock and a real socket, a silent upstream that used to hold a two-message read for up to
four minutes was cut at a 1 s allowance in 1.00 s (`test_a_silent_upstream_is_cut_at_the_
allowance_on_a_real_clock`, marked `network`, runs on request).

**2. A Gmail fault's decline says what can be done about it.** `RecoveryKind` lives on each
fault type beside its D.11 code: `narrow`, `retry_later`, `reauthorise`, `none`. The
`GmailFault` clause reads it; `terminal` is true for the last two. Every refusal now carries
a `recovery` token (`partition.RECOVERY_TOKENS`) and its text mirror a `recovery:` line. A 404
is `terminal: true, recovery: none`, names the endpoint, and **does not probe whether the
identifier is a thread**; that question was recorded as open and stays open. The two sentences
that ran together on the wire are separated.

**3. Every row states who its `From` header named and when Gmail received it.**
`MessageRow.attribution` (`Attribution`: `provenance`, `address`, `display_name`,
`stated_addresses`) is built by one function for search rows and read rows alike. The address
is the header's addr-spec, folded; the display name is fenced as untrusted header text; there
is no `sender`, `author` or `verified` field, and the model's validators refuse an address
with no header behind it. `internal_date` is on every row, `null` when unobserved, with
`internal_date_provenance` beside it (`gmail_internal_date` / `not_observed`). The A6 test
that asserted the omission was amended to assert the explicit form, and says why.

**4. Call lifecycle diagnostics, opt-in.** `mailweave/diagnostics.py`, enabled by
`MAILWEAVE_DIAGNOSTICS=<file>`, wired into the one partition both surfaces pass through. One
line per start, one per end, with elapsed ms and outcome; argument **shapes** only, never
values. The startup banner reports it. Added to the audited-writer allowlist. It records that
a call happened and how it ended; it does not record results and cannot verify a citation,
which needs the tool results preserved separately.

Field census: 310 → 315. Wire additions are additive; the v0.1 input contract is untouched.

**Two things the full suite found that the four repairs then had to include.** Every row is
heavier by its attribution and chronology fields, and the disclosure estimate did not charge
them, so the near-cap Harbor fixture rendered 244 characters over the host cap and was
refused; the charge is now on the row (`envelope/measure.py`, `ROW_ATTRIBUTION_CHARS`),
carried by the same channel as the authentication record through `structure/threadmap.py`,
`disclosure/plan.py`, `disclosure/pages.py` and `disclosure/layout.py`. And the heavier rows
pushed a near-cap Orivra answer into the budget-compaction step for the first time in the
fixture matrix, which exposed that the digest the compaction ladder has emitted since
2026-09-19 was never in `orivra_ask`'s published output schema. The schema now admits both
forms (`oneOf`), and a test validates the digest against it.

**Fixtures that sat at the host cap, recalibrated by measurement, not loosened.** Four tests
asserted figures that a heavier row moves: `test_round25`'s three near-cap ceilings and its
step-7 fixture were re-derived from the new row cost (the structural term now includes
`ROW_ATTRIBUTION_TOKENS`; ceilings 15,200 / 14,200 / 13,000; step-7 bound 22,000 against a
measured 21,276), `test_round28`'s recommendation fixture from 85 words to 62 (measured window
56–67), and `test_injection_ws14`'s paired bait comparison from eight noise threads to five,
because the baited four-source layout was estimated at ~25.3k characters against the 25k host
cap and the fourth source, `t-true2`, was withheld under the disclosure ceiling - the cap, not
the ranking the test is about. Its assertion is unchanged; its failure message now names the
cap that took a thread, if one did. One replant anchor (`R73`) was re-pointed at the six-line
call it now mutates. And the first draft of the row-cost change declared a second
`DISPLAY_NAME_TOKENS` in `measure.py`, shadowed by the participant index's existing one; the
duplicate is gone and the row charges the participant's measured pair, which is the same
`Content` object.

**Second repair, same day: two gaps the first four left.** (1) The deadline was enforced per
socket operation and not per call. `httpx` has no total-time timeout; a body that arrived a
few bytes at a time inside every read window, and the access-token exchange that runs before
the first attempt under the token endpoint's own 30 s, both walked past the allowance. The
bound now lives at the socket: `net/deadline.py` wraps the `httpcore` network backend so every
read, write, connect and handshake is clamped to what is left of the deadline the call bound,
published through a `ContextVar` that `in_band` scopes to the call. No thread, no interruption
(AD A.5c's single loop is kept); the transport's own timeout fires at the allowance. The one
private attribute it touches (`HTTPTransport._pool._network_backend`) is asserted at
construction and pinned to the locked `httpx 0.28.1` / `httpcore 1.0.9`. A token exchange the
clamp cuts is raised as `GmailDeadlineExceeded` in a `credential` phase and declines
`budget_exhausted, retry_later` - not `auth_reauth_required`, which is what a `ConsentFailed`
from a slow endpoint used to become. The regressions run the real `httpx`/`httpcore` stack
over a scripted socket on a real clock: a trickling body and a stalled token endpoint are both
cut at a 400 ms allowance inside the tolerance; without the clamp the same calls took 1.2 s
and 10 s. The end line now carries `allowance_ms`, `overrun_ms` and `cold_load_ms`, and
`tools/dev/check_calls.py` reads a file the way the retest must: a late `budget_exhausted` is
late. (2) The diagnostic's start line was written before validation and named every key the
caller sent, carrying the value of any key it took for an enum; a key or a short string was
therefore a channel into the file. Shapes are now read off the tool's published schema: a key
is named only when the schema publishes it, a string carried only when the schema publishes an
enum it belongs to, integers are always `int`, and a tool with no schema names nothing. Held by
malformed-input regressions through both tool boundaries. Not changed: the recovery schedule
(`surface/recovery.py`), which offers a single `body_clean` message no narrower form and so
declines a deadline on it `retry_later`; noted, not repaired.

**Retest run 1, 2026-09-22: failed, preserved, and what it showed.** Run under
`RETEST_2026-09-21.md` with diagnostics **off** - the variable was exported in a shell and
Claude Desktop does not pass a shell's environment to the server it spawns; the fix is an
`env` block in the server's Desktop config entry, now in the retest's step 3. The server log
(`mcp-server-orivra.log`, held privately with the run) carried repeated `ValueError:
do_handshake_on_connect should not be specified for non-blocking sockets` from
`net/deadline.py`'s TLS handshake. Mechanism, confirmed by reproduction on the real
`httpcore.SyncStream` over a real socket: once a call's allowance was spent, the clamp handed
the next socket operation a timeout of `0.0`; a zero socket timeout is non-blocking mode,
`ssl.SSLContext.wrap_socket` refuses a non-blocking socket with that `ValueError`, nothing in
`httpcore` or `httpx` maps it, and it left `GmailClient._request` as a bare exception - an
internal error to the client, not the `budget_exhausted` decline the deadline exists to
produce; the client retried and hit it again. (A zero-timeout read or write is a
`BlockingIOError` by the same mechanism, mis-classified as `upstream_unavailable`.) Repaired
by refusing the operation with the transport's own typed timeout - `ConnectTimeout` for a
connect or handshake, `WriteTimeout`, `ReadTimeout` - before the transport is entered
(`allowance`), which `_request` reads as the deadline's; nothing is extended and nothing
sleeps. Regressions spend the deadline immediately before each boundary on the real stream
and assert the operation was never entered; the `tls` case reproduces the retest's exact
error when the refusal is removed.

**Run 1's timings, as read from the Desktop log (recorded, not attributed).** Four of the
run's calls - the 7th, 8th, 10th and 13th - ran approximately 104, 110, 110 and 110 seconds
between the request and the `ValueError`. In every one the traceback lay inside the retrieval
ladder's `list_messages` (`messages.list`), not in a post-semantic disclosure fetch. Those
intervals are an order of magnitude past the largest allowance a single retrieval binds
(13,700 ms), and this record does not say where they went: not to name resolution, not to
Gmail, not to the lock, not to a chain of retrievals. The exception repair above is one
thing; the excessive duration is another, and it is open.

**Two facts from the source, found while reading it for run 1, fixed the same day, and
not offered as the explanation.** (1) The Orivra adapter opened `service.open_client()`
directly for its own Gmail requests - the ids-only ladder (which is `list_messages`), the
liveness probe, the item fetches, the history walk and the version probe - so those requests
ran under **no** deadline: the first repair's "every tool, not only search" had covered the
four MailWeave tools and not the adapter's own calls. Every one now goes through
`MailweaveService.client_for_call()`, the same construction the tools use. (2) The socket
clamp was published when a deadline was bound to a client and left in the call's context
until the call ended, so a client opened with no deadline was clamped by whichever deadline
the previous client had left there, spent or not, while its own `_request` had no deadline
to read the cut as. The clamp is now published per request, around the request, by the
client making it (`net/deadline.py::published`). Both are held by regressions in
`tests/test_repairs_2026_09_21.py` §8 that fail when reverted. Whether either produced run
1's 104-110 s is not established: a deadline-less request under the transport's 30 s
per-operation defaults and four attempts is consistent with an interval of that size and
with a much shorter one, and the log's intervals alone do not pick a shape. Run 2, with
diagnostics on, is what says where the time went: `queued_ms` on the start line (the wait behind the
one-call-at-a-time lock, which the client's clock includes and `elapsed_ms` does not), and on
the end line `deadlines` (how many retrievals bound an allowance), `allowance_ms` (their
sum), `sockets`, `connect_ms` (name resolution included), `tls_ms`, `write_ms`, `read_ms` and
`cold_load_ms`.

**Retest run 2, 2026-09-22: answers for both questions, preserved, and an output gap.**
The second live run under `RETEST_2026-09-21.md` completed both questions and is preserved
privately as run 2 beside run 1 - the answers and every raw tool result, and the diagnostics
file where the run wrote one; nothing of either run is in the repository. Reviewed under Part
two against the preserved results: the decision question (the retest's first, Question 2 of
the campaign) is **resolved** - the cited ids are in the results, the decision and its reasons
are in cited rows, and the answer's own separation of statement from inference matches the
checks. The two-threads question (the retest's second, Question 4) is **partially resolved**:
the connection rests on cited rows, and the chronology claim does not - the answer's
ordering of the two threads was not read off `internal_date`, because the text the Desktop
surface reads carried none. That is the output gap: `MessageRow` had carried `attribution`
and `internal_date` with their provenance since repair 3, and `surface/rendering.py` - the
text mirror, the only half a text-only client sees - mirrored neither. The structured form
said who each header named and when Gmail received each message; the text said nothing, and
the client read both out of body text again, which is the finding of the first five runs
with the fields present and invisible.

**Third repair, same day: the text mirror carries the fields.** Every row's line in the text
is now followed by `attribution <provenance>: address <a>, stated_addresses <n>`, a fenced
`display_name (untrusted_third_party) <<<...>>>` line when the header carried one, and
`internal_date <stamp> (<provenance>)` - the same four attribution states and two chronology
states the structured form keeps apart, spelled with the same tokens, so `headers_not_observed`
and `from_header_absent` are different lines and `internal_date none (not_observed)` is a
statement rather than a missing line. The address is a bare token because `is_an_address`
admits no whitespace; the display name is fenced because it is sender-chosen text, as a body
is. One sentence at the head of every response that carries rows (`ATTRIBUTION_NOTE`) says
what the lines are and are not: the `From` header as Gmail returned it, not an authenticated
identity; `internal_date` as when Gmail received the message, in epoch milliseconds. Each new
line is a `MIRRORS` entry that round-trips (`tests/test_mcp_surface_round24.py`), and a
display name shaped like one of the mirror's own lines is read by nothing: the readers take
fenced blocks out first, by the nonce on the block. `tests/test_text_mirror_attribution.py`
drives the shipped server behind a real MCP client and reads **only the text blocks**; the
renderer was mutated five ways - the lines removed, the name unfenced, the chronology
provenance token replaced, the note omitted, the `none` of an unobserved address blanked -
and each mutation fails the file (the first, five of its seven tests).

**The caps, held by measurement.** The wire grew, so the estimate that keeps a response under
the host's 25,000-character result cap was re-measured with the wire's own serialiser rather
than guessed at: `ROW_ATTRIBUTION_CHARS` 205 to 345 and `ROW_ATTRIBUTION_TOKENS` 13 to 22
(the structured fields plus the two mirror lines, at the widest closed-vocabulary values), a
row's display name charged by `ROW_DISPLAY_NAME_CHARS` 202 / `ROW_DISPLAY_NAME_TOKENS` 10 (the
`Content` object over the null it replaces, plus the fenced line) rather than the participant
index's pair, the address and the name each charged once as JSON and once as text, and
`RESPONSE_STRUCTURAL_CHARS` / `_TOKENS` raised 2,600 to 2,850 and 500 to 540 for the note.
`test_the_attribution_note_is_charged_at_its_measured_size` recomputes every figure and holds
each constant above it. Two sizing corrections found on the way: the thread-map page probe
priced a row's display name as a one-word name, so a multi-word name was under-charged in
tokens, and `attribution_chars` measured the address and name unescaped, so a name with
quotes or non-ASCII was under-charged in characters on the JSON half; the probe now charges
the wordiest name the thread's longest display name can hold, and the map measures the pair
as the wire escapes them. **Seven fixtures that sat at the cap moved, and each was re-measured
on the shipped tools rather than loosened:** the near-cap Orivra mailbox in
`test_orivra_text_only_protocol` and `test_orivra_equivalence` from 8 body repeats to 4 (three
rows fit the whole cap and two the container from 1 to 6; the old composition is over the cap
at every one), `test_round28`'s recommendation fixture from 62 words to 36 (window 33-40) and
its every-row-at-depth fixture from nine bodies to six at the default 40 words (nine no longer
fit at any body length), `test_round25`'s three step-8 ceilings to 15,700 / 14,640 / 13,380
(windows 15,600-15,800, 14,540-14,740, 13,280-13,480), `test_disclosure_round23`'s snippet
tier ceiling from 5,500 to 5,800 (window 5,600-6,050; at 5,500 the floor was all runs, which
is not a tier), and `test_navigation_and_disclosure`'s largest requested batch from 12 rows to
10 (eleven snippet rows fit one response, twelve do not) and its width-change thread from 90
messages to 60 (the wide record moves the width from 30 to 68 messages and from 105, and not
in between), and `test_integration_repair_2026_09_15`'s broad-query fixture from 20-character
message ids to Gmail's own 16 (the widest width that fits its retry fell from 6 to 5 of an
applied 11, exactly the halving the test holds the retry to beat; at 16 it is 6 again and the
other two tests on that fixture are unchanged). Not changed: retrieval, the questions, the
mailbox, the ranking, the ladder's steps, the recovery schedule. `ruff`, `mypy` and the
guards are clean on the tree.

**One fixture the measurement could not recalibrate, and the adjustment the owner then
authorised.** The evaluation harness's self-test has a `selftest-window` case whose purpose is
to make the fixed-window baseline (Baseline F, the `+/-2` arm H3 is compared against) reach
its fill stage, so that a `window +/-k around <hit>` row is rendered and checked
(`tests/test_evaluation_harness.py::test_baseline_f_executes_and_its_rows_say_why_they_are_
there`). The fill survives only when the whole conversation fits the host cap, because the
ladder's first step reduces fill rows. On the smoke corpus the one candidate that filled - a
ten-message conversation with three hits, query `dropped` - was 594 characters under the cap
in the estimate on 2026-09-21 and is 1,278 over it now: the mirror's two lines and the note
add about 1,600 real characters to that response, more than the room it had. Every candidate
the case-file probe admits was measured (144 conversations of ten to eighteen messages, and
the seven of six to nine); every other one's rarest word reaches two or more conversations,
so none fills, and a two-word query broadens rather than narrows under the ladder's
relaxation. Nothing in the existing test fixtures moved it, so the test was left red and the
decision put to the owner.

The owner authorised a narrowly scoped adjustment to the offline self-test fixture, and that
is all that changed. **The fill is now observed on a small, deterministic synthetic
conversation** (`window_conversation()` in the test file): seven messages in one reply chain,
one hit at position 3, short fixed bodies, one unrelated thread beside it. It is built through
the same arm constructor the campaign uses (`dummy_arms`, `FIXED_WINDOW`) and searched through
the shipped pipeline at the **unchanged** ceilings; the response renders about 15,000
characters and no ladder step touches it. The test asserts that exactly positions 1 and 5
carry `WindowOffset` rows, each anchored on the hit with the signed offset its position
implies and rendering `window -2 around bf-003` / `window +2 around bf-003`, each carrying
text; that the `+/-1` neighbours are the reply floor that outranks the fill; that the same
reasons end the rows' lines in the text mirror through the tool boundary, under the host cap;
and that the query-aware arm on the same conversation fills neither position. The corpus half
of the test is kept - the arm executes every case and every row states a reason - and it keeps
its refusal to swallow exceptions. Mutation check: the replant R232 (`_fill_reason`'s window
branch disabled) still fails it, and so do a radius of 1, a radius of 3 and a flipped offset
sign. Nothing about the assertion was weakened: zero fill rows fails it, and so does any
number other than the two the mechanism implies.

**The near-cap case is kept separately, as evidence of the real size trade-off**
(`test_baseline_f_near_the_cap_trades_its_window_for_declared_recoverable_runs`). The `dropped`
conversation is pinned by thread and query, both checked against the corpus. Through the tool
boundary it must be served under the cap and declare the trade in both halves (`partial`,
`truncated_by: mailweave`, the disclosed-token cap in `budget_caps_hit`, the omission's
host-cap sentence, the mirror's header line); keep every hit at body depth; account for every
position of the thread as a row or a member of a declared run; give every window position it
still carries a real reason; and put every traded window position (today 3 and 4) in a run
whose line the text prints and whose own call returns it at its position, with that row's own
call reading its content. Collapsing the runs out of the text fails it. Not changed: the
production caps, retrieval, the ladder, the smoke profile, the case-file construction in
`mailweave_harness.evaluation.selftest` and the probe in `tests/fixtures/eval_dummy.py`. One
consequence recorded rather than changed: the probe no longer finds a filling conversation
on the smoke profile, so the case file's `selftest-window` case falls back to its first
admissible conversation (query `warehouse`, which the ladder reduces heavily); its note still
says it exists to make the baseline fill. That construction is the harness's and its live
self-check's, and is left for the evaluation programme. With the adjustment the full offline
suite is 4,540 passed, 5 skipped, 0 failed, the replant manifest included; `ruff`, `mypy` and
the guards are clean on `server/` and `orivra/`.

**Pre-existing, not touched, and a blocker for the push:** under the locked tool versions
(`ruff 0.16.5`, the locked `mypy`), the tree *before* these repairs fails `ruff check`, fails
`ruff format --check` on 45 files, and reports 236 `mypy` errors in 45 files - none of them
in the files changed here, which add zero. CI runs those three with `--frozen`, so the first
push will be red on lint, format and types from files this repair did not open.
