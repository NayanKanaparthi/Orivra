"""Size measurement of an assembled response, and the ladder artifacts that shrink it.

Kept in its own module so that `response.py` can enforce the ceiling as a property of the
type rather than as a step the builder is trusted to run (DISC-06, R-DISC-002).

**What is measured is what is sent** (round 25, R-DISC-019/022, R-MCP-003). Until this
round the estimate counted disclosed body text plus a flat 40 per stub row and per
collapsed run, and counted *nothing* for the structure around a row - no key, no id, no
position, no role, no reason, no linkage, no provenance, no `unabridged` affordance - and
nothing for the text mirror the client receives beside `structuredContent`. Three findings
turned out to be that one defect seen from three sides:

  * a `snippet -> stub` degradation *raised* the estimate, because a stub was charged 40
    and a snippet only its (<= ~36-token) text, so A.9a's ladder could enlarge the thing it
    was degrading;
  * the enforced quantity was 1/20th to 1/85th of the rendered response, and the ratio moved
    with row count, so no choice of ceiling made it an upper bound;
  * following the server's own collapsed-run affordance returned 272 % over the declared
    ceiling with `truncated_by: null`.

**The rule, from amendment A11.** *A row is charged its structural cost at every depth.* A
row costs `ROW_STRUCTURAL_TOKENS` for existing at all, plus its disclosed text once for each
copy of that text the wire carries (`WIRE_COPIES_OF_DISCLOSED_TEXT`: the structured payload
and the text mirror). A collapsed run costs one row's structure plus a per-member charge for
the ids it lists. A response costs `RESPONSE_STRUCTURAL_TOKENS` for the blocks every
response carries whatever else it holds. Every one of those is a constant a *measurement*
pins - `test_the_estimate_is_an_upper_bound_on_the_rendered_wire` renders responses across
the shape matrix and asserts the estimate bounds the wire - rather than a number chosen to
make an arithmetic come out.

**The consequence, stated plainly.** Charging structure makes every response measure larger,
so a ceiling that used to admit 225 stub rows now admits far fewer. That is the honest
direction: the old number admitted 225 rows *and then the host cut them*. The ceiling
figures themselves are `[DESIGN, set by PF-6]` and this module does not move them; what it
moves is the quantity they are compared against.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from mailweave.content.reductions import Reduction, ReductionKind
from mailweave.envelope.fence import unfence
from mailweave.envelope.vocab import Depth, WithheldCap
from mailweave.envelope.wire import (
    PARTICIPANT_ROLES,
    Affordance,
    AskedFor,
    AttachmentMetadata,
    Continuation,
    ErrorEntry,
    NotTriedEntry,
    ScanScopeEntry,
    ThreadParticipant,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to the type checker
    from mailweave.envelope.response import Envelope

#: What one wire row costs before any of its text: the JSON object's keys and values (id,
#: position, role, reason, depth, linkage, reply parent, provenance, coverage, the
#: `unabridged` affordance) plus the row's line in the text mirror. **Derived by measuring
#: the rendered form**, not chosen: `test_the_estimate_is_an_upper_bound_on_the_rendered_wire`
#: renders whole responses and fails if this is too small, and
#: `test_a_row_costs_its_structure_at_every_depth` fails if a depth escapes the charge.
ROW_STRUCTURAL_TOKENS = 120

#: What INJ-05's per-message fields cost a row *before* any authentication record:
#: `headers_observed`, `reply_to_differs`, and either `authentication: null` or the
#: `{recorded: null, oversize: true}` object a row states when the header was there and was
#: longer than `MAX_AUTH_RECORD_CHARS`. **The oversize object is the larger of the two and is
#: what this bounds**, at 9 whitespace tokens and 110 characters measured off `json.dumps` of
#: the three fields with their separators - the first draft charged 12 and 90, which was over
#: on tokens and *under* on characters for exactly the row that declares a record it does not
#: disclose. A disclosed record is charged on top, by `AUTH_RECORD_TOKENS`/`AUTH_RECORD_CHARS`
#: plus the record itself, and **measured** rather than bounded: charging
#: `MAX_AUTH_RECORD_CHARS` on every row would put 512 characters against a field that is
#: usually thirty, an over-estimate large enough to degrade responses that fit.
ROW_IDENTITY_TOKENS = 9

#: What every row's attribution and chronology fields cost before any address or name
#: (2026-09-21): the `attribution` object with `provenance`, a null `address`, a null
#: `display_name` and `stated_addresses`, plus `internal_date` and
#: `internal_date_provenance`. Both are on every row now, so both are structural. Measured
#: off `json.dumps` of the widest closed-vocabulary values: 13 whitespace tokens on the
#: structured form, **plus the text mirror's two lines for them** (2026-09-22): `attribution
#: <provenance>: address <a>, stated_addresses <n>` is 6 tokens and `internal_date <stamp>
#: (<provenance>)` is 3. The mirror did not carry these fields until then, and an estimate
#: that charged only the structured half would have handed the difference to the host.
ROW_ATTRIBUTION_TOKENS = 22
#: A row's `From` display name, when it carries one: the `Content` object that replaces the
#: `null` under the `display_name` key on the structured form (6 whitespace tokens more than
#: the null, measured) and the fenced `display_name (<trust>) <<<...>>>` line the mirror
#: renders it on (4). The name's own words are counted beside this, once per form. **Not**
#: the participant index's `DISPLAY_NAME_TOKENS`: that entry sits in a list with no key and
#: no mirror line. The address costs no token of its own: it replaces the `null` and the
#: `none` the scaffolding already charges, and `is_an_address` admits no whitespace.
ROW_DISPLAY_NAME_TOKENS = 10

#: The JSON scaffolding of a *disclosed* authentication record in whitespace tokens: the
#: `recorded` object's keys, its two closed-vocabulary values, the `oversize` flag and the
#: fence markers around the header. The header's own words are counted beside this. Measured:
#: a realistic `Authentication-Results` row renders 20 tokens of which 5 are the header.
AUTH_RECORD_TOKENS = 12

#: How many times the wire carries a row's disclosed text. **Two**, and both are things the
#: client receives: once inside `structuredContent`, once in the text mirror that MCP-03
#: requires beside it. Counting it once was half of why the estimate was 20x from the wire.
WIRE_COPIES_OF_DISCLOSED_TEXT = 2

#: What one collapsed-run member costs in the token estimate: its id, listed once in
#: `member_ids` (navigation redesign, 2026-09-14; the run's affordance names a page and
#: lists no ids), with its quoting.
COLLAPSED_RUN_MEMBER_TOKENS = 3

#: What one `withheld` record costs: its id, thread id, cap, `why` sentence, its line in the
#: text mirror, and the executable affordance beside it - which is a **separate** entry in the
#: response's `affordances[]` block and was charged nothing until round 26. A record is
#: cheaper than the row it replaces - which is what keeps A.9a steps 7 and 8 reductions - and
#: it is emphatically not free: a response that withheld four hundred messages used to declare
#: 500 tokens and render 22,000.
WITHHELD_RECORD_TOKENS = 60

#: One `withheld_groups[]` entry's tokens (round 29). Its measured character cost is 0.63 of a
#: not-included entry's; this is taken as 0.82 of that entry's 55, deliberately above the
#: character ratio, so the token estimate errs high exactly as the character estimate does.
WITHHELD_GROUP_TOKENS = 45

#: What one `Source` costs before its rows: the thread id, the four counts, both freshness
#: stamps, the signed `map_id` handle, the structural report, and the source's own line in the
#: text mirror.
#:
#: **Charged from round 26** (R-DISC-032's rule, applied past the field it names). A source
#: was worth nothing in this estimate until now - only its rows were - so a twelve-thread
#: search and a one-thread search of the same row count measured the same, and A.9a step 7,
#: whose whole job is to remove a source, could see no saving in removing one. That is why a
#: response of twelve one-row sources could not be brought inside the host's cap by the step
#: written to do exactly that.
SOURCE_STRUCTURAL_TOKENS = 60

#: What one `not_included_sources[]` entry costs: the thread id, its stated total, the `why`
#: sentence, the map affordance it carries, that affordance's own entry in `affordances[]`,
#: and the entry's line in the text mirror.
#:
#: **Charged from round 26** (R-DISC-032's rule, applied past the field it names). The block
#: scales with the response - A.9a step 7 files one entry per source it splits off - and was
#: charged nothing, which was invisible while the ceiling sat at 9,000 tokens and every
#: response was far inside it. It stops being invisible the moment a ceiling is lowered to
#: meet the host's character cap, because then the estimate is what the response is held to.
NOT_INCLUDED_SOURCE_TOKENS = 55

#: What every response costs whatever it carries: `retrieval_report`, `asked_for`,
#: `scan_scope`, `counters`, `ceiling`, `budget`, the freshness stamps and the mirror's own
#: header and residue lines. A constant on both sides of the estimate, so it cannot make the
#: ladder's number and the envelope's number disagree.
#: **Raised from 500 to 540 on 2026-09-22** for the mirror's one-sentence attribution note
#: (`surface/rendering.ATTRIBUTION_NOTE`, 38 whitespace tokens), rendered once on every
#: response that carries a source. `test_the_attribution_note_is_charged_at_its_measured_size`
#: holds the constant above the sentence.
RESPONSE_STRUCTURAL_TOKENS = 540

#: What one `ThreadParticipant` costs before the messages it cites: its address, its five role
#: keys, `distinct_display_names` and the computed `wrote_here`. **Fifteen, and the figure is
#: measured rather than chosen**: `participants_tokens` reproduces the rendered participant
#: block exactly - 2, 13, 31 and 68 participants over 24, 24, 60 and 540 citations all come
#: out to the token, because an address cannot contain whitespace (`constants.is_an_address`)
#: and every other member of the model is a key, a bracket or an integer.
#:
#: **Why this exists at all** (round 26, R-DISC-032). `measure_tokens` charged the rows, the
#: collapsed runs and the withheld records, and charged `Source.participants` **nothing** -
#: while participants were 82 % of the rendered response on a 400-sender thread. So the
#: round-25 headline property, *the estimate is an upper bound on the rendered wire in its own
#: token unit*, was false from about 25 distinct senders up, and 11.5x wrong at the worst
#: measured shape. The test certifying it varied response size across six values and held one
#: sender at every one of them.
#: **Round 31 raised it from 15 to 18, measured.** An empty participant record renders as 18
#: whitespace tokens - eight keys, their closed values and the address - and INJ-05's
#: `display_names` key is two of them. Fifteen was already one short of the round-26 shape;
#: the shortfall was invisible because every real participant carries citations, which are
#: charged on top and covered it. `test_the_participant_index_is_charged_what_the_wire_carries`
#: writes the oracle out by hand and is what caught it.
PARTICIPANT_STRUCTURAL_TOKENS = 18

#: What one citation inside a participant record costs: the quoted message id, its comma and
#: the space after it, which the whitespace count sees as one token. A message can be cited by
#: one participant under more than one role, and each citation is charged, because each one is
#: a separate entry on the wire.
PARTICIPANT_CITATION_TOKENS = 1

#: One display-name entry's scaffolding inside a participant record: the `Content` object's
#: own keys, its trust and source values, and the fence around the name. The name's own words
#: are counted separately, because a sender picks how many there are.
DISPLAY_NAME_TOKENS = 12

#: The smallest `budget.max_disclosed_tokens` a caller may ask for: the response-level
#: structure plus one row. **Derived from the two constants above rather than chosen**, so it
#: follows them. Below it no response can be built at all, and a published argument whose
#: small values are all unbuildable is the defect R-MCP-004 filed one value up.
MINIMUM_DISCLOSED_TOKEN_REQUEST = RESPONSE_STRUCTURAL_TOKENS + ROW_STRUCTURAL_TOKENS

#: Stub rows and snippets cost tokens too; A.9a's ladder counts map tokens (DISC-04). A stub
#: row is exactly a row with no text, so this **is** the structural charge rather than a
#: second number that could drift from it. `disclosure/segments.py` derives the flat-map
#: boundary from it, and that derivation now uses a figure that reflects the wire.
STUB_ROW_TOKEN_ESTIMATE = ROW_STRUCTURAL_TOKENS


# --- the same inventory, in the unit the HOST enforces (round 26, R-DISC-033/R-MCP-021) ----
#
# **Why a second unit rather than a conversion.** The token estimate above is enforced against
# the ceilings AD D.4 publishes; the host enforces a *character* cap on the rendered
# `CallToolResult`, and no ratio between the two is a bound - a response of many short rows
# and one of few long ones sit at opposite ends of it. So the same inventory is priced twice,
# in both units, off the same objects, and the ladder fits both.
#
# **Where a figure is exact it is computed and not estimated.** A row's disclosed text, a
# participant's address and every message id are values the layout is holding, so they are
# measured rather than guessed at; what is left is the JSON scaffolding around them, and each
# constant below is the measured residual of the rendered form over a shape matrix that varies
# distinct-sender count, recipient-list length, subject length, body length, message-id length
# and response size (round 26's `test_the_character_estimate_bounds_the_rendered_result`).
# Every one of them is an over-estimate on every shape measured, and that direction is the
# point: an estimate that under-charges hands truncation to the host, which is the defect.

#: The blocks every response carries whatever else it holds, as characters: the retrieval
#: report, `asked_for`, `scan_scope`, the counters, the ceiling and budget blocks, the
#: freshness stamps, and the text mirror's own header and residue lines. **Raised from 2,600
#: to 2,850 on 2026-09-22** for the mirror's attribution note (241 characters and its line
#: break, taken to 250); see `RESPONSE_STRUCTURAL_TOKENS`.
RESPONSE_STRUCTURAL_CHARS = 2_850

#: One source's own scaffolding, before its thread id: the four counts, both freshness stamps,
#: the `map_id` handle (a signed, self-describing token of a few hundred characters), the
#: structural report, and the mirror's `source thread ...` line.
#:
#: **Round 27, R-MCP-024.** This was 1,100 and was not a bound: measured against the rendered
#: form on the *served* path, the wire carried 289 to 386 characters more per source than the
#: estimate charged, so the deficit grew linearly with source count and the estimate crossed
#: below the rendered size at three sources. Round 26's matrix held source count at one on
#: every one of its ten shapes and drove `assemble` directly rather than the served path, which
#: is why a constant that fails on source count read as an over-estimate on all ten.
#:
#: The residual splits cleanly into a flat part and a per-thread-id-character part of slope
#: 5.7 (the thread id is rendered about six times per source: the `thread_id` key, the map
#: affordance, the `map_id` payload, the structural report and both mirror lines), so the id
#: is charged off its own length like a row's and this constant is what is left: 1,354-1,359
#: measured across thread ids of 5, 16 and 22 characters, taken to 1,400.
SOURCE_STRUCTURAL_CHARS = 1_400

#: How many times a source's own thread id is rendered. Counted as a multiple of the **actual**
#: thread id rather than folded into the constant above, for the reason `ROW_ID_COPIES` gives:
#: a Gmail thread id is longer than a fixture's and the estimate must not depend on which it
#: meets. Measured slope 5.7, charged at 6.
SOURCE_ID_COPIES = 6

#: The recommended expansion's scaffolding (round 28): the `affordances[]` entry's keys and
#: closed-vocabulary values, plus the mirror's `next call ... {...}` line, before the ids it
#: names. Charged on every response whether or not one is emitted, which is the over-estimate
#: direction; the ids are charged off their own length beside it. Measured on the twelve-hit
#: shape: entry 133 + line 115 = 248 characters naming five six-character ids, of which 188
#: is scaffolding and separators; taken to 240.
RECOMMENDED_EXPANSION_CHARS = 240

#: How many times the recommendation renders each id it names: once in the JSON entry, once
#: in the mirror line.
RECOMMENDED_EXPANSION_ID_COPIES = 2

#: One row's scaffolding before its id and its text: the JSON keys and closed-vocabulary
#: values of `MessageRow` (role, depth, linkage, provenance, coverage, reductions, the
#: `unabridged` affordance, the reason), plus the row's line in the text mirror.
ROW_STRUCTURAL_CHARS = 840

#: INJ-05's per-message fields in characters, before any *disclosed* authentication record:
#: two booleans and the larger of `authentication: null` and the oversize declaration. See
#: `ROW_IDENTITY_TOKENS` for why this is the oversize object and why the record is measured.
ROW_IDENTITY_CHARS = 110

#: The attribution and chronology scaffolding in characters; see `ROW_ATTRIBUTION_TOKENS`.
#: Measured with the wire's own serialiser (`json.dumps`, default separators) at the widest
#: closed-vocabulary values, a 20-digit stamp and three digits of `stated_addresses`: 119 +
#: 92 on the structured form, and 73 + 61 for the mirror's two lines (2026-09-22). The
#: address and the name are charged beside this, each at its own measured length.
ROW_ATTRIBUTION_CHARS = 345

#: A row's `From` display name in characters, before the name itself: the `Content` object
#: that replaces the `null` under the `display_name` key (114 more than the null, measured
#: with an empty name) and the mirror's fenced line around it (88: prefix, trust token, both
#: fence markers, line break). The name is charged beside this, once as JSON and once as
#: text. See `ROW_DISPLAY_NAME_TOKENS` for why this is not the participant index's
#: `DISPLAY_NAME_CHARS`.
ROW_DISPLAY_NAME_CHARS = 202

#: The fence, `Content` object and JSON escaping around an authentication record that is
#: present. Its own characters are counted beside this.
AUTH_RECORD_CHARS = 130

#: How many times a row's own id is rendered: the `id` and `thread_id` keys, the affordance
#: that fetches it, the mirror line, and the reason parameters that name it. Counted as a
#: multiple of the **actual** id length rather than folded into the constant, because a Gmail
#: message id is longer than a fixture's and the estimate must not depend on which it meets.
ROW_ID_COPIES = 8

#: What fencing one row's text costs, in both copies: `envelope.fence`'s open and close
#: markers carry the per-response nonce, and JSON-escaping the fenced string adds its own.
FENCE_CHARS = 128

#: One collapsed run's scaffolding, before the ids it lists: its positions, its count, its
#: `why`, its expansion affordance, and the mirror's `collapsed positions ...` line. Round 29's
#: certification (`test_a_collapsed_run_is_charged_at_or_above_what_it_renders`) found 400
#: two characters short on a one-member run at every id width, once the member's third id
#: copy was charged where it belongs; taken to 440.
COLLAPSED_RUN_CHARS = 440

#: The separators and quoting around one collapsed-run member id, and how many times the id
#: itself renders beside them.
#:
#: **History, because the number has moved twice and each move was a measurement.** Round 26
#: charged the id twice: `member_ids`, and the `mailweave_get_messages` call the run's
#: affordance minted with every member listed again. Round 29's review (R-V01-005) found a
#: third copy - the affordance's twin in `affordances[]` - and took the count to 3, measured on
#: the real serializer at 706 / 3,410 / 18,414 characters for 5 / 50 / 300 members (a flat 400
#: plus 12 per member plus 3.0 per id character).
#:
#: **The navigation redesign (2026-09-14) removed the ids from the affordance.** A run now
#: points at a *page* of the thread's map (`mailweave_thread_map(thread_id, page)`) on the
#: expansion path and at the map or its segment on the search path, and the expansion path
#: no longer twins the affordance. A member's id renders once, in `member_ids`, on both paths,
#: and the count says so; `test_a_collapsed_run_is_charged_at_or_above_what_it_renders`
#: certifies the charge against both forms at every id width. The per-member scaffolding is
#: what one JSON list entry costs - `"…", ` is four characters - plus two of slack; the 16 of
#: the three-copy era was three entries' worth and, kept, made a 600-message inventory cost
#: 7,200 characters it never rendered, which is a page of stub rows the reader did not get.
#: Measured on the serializer at 1 / 5 / 50 / 300 members and 1 / 16 / 30-character ids.
COLLAPSED_RUN_MEMBER_CHARS = 6
COLLAPSED_RUN_MEMBER_ID_COPIES = 1
#: How many times the run's **thread** id renders: in the run's `thread_map` affordance and,
#: on the search path, in that affordance's twin. Charged off the id's measured width rather
#: than folded into the flat figure, because a thirty-character thread id twice is sixty
#: characters the flat figure was two short of (found by the certification at width 30).
COLLAPSED_RUN_THREAD_ID_COPIES = 2

#: One `withheld` record's characters: its id, thread id, cap token, `why` sentence, the
#: executable affordance beside it, that affordance's own entry in the response's
#: `affordances[]` block, and **two** mirror lines - the record's and the affordance's. The
#: text mirror renders every affordance as a line of its own, which is why a record costs more
#: than its JSON.
#:
#: **Round 27, R-MCP-024.** This was 700 flat and over-charged by 293 characters per record on
#: the shape it is reached by. That direction is safe on its own and was not harmless: a search
#: over thirty one-message threads degrades until every message is a withheld record, and at
#: 700 each the estimate of that end state was ~32,000 characters against a 25,000 cap, so the
#: ladder could not converge and an ordinary wide search declined **with no mail at all** while
#: the response it refused to send would have rendered well inside the cap.
#:
#: Measured the same way as the source constant, the record's cost is 369 + 4 x (thread id) +
#: 2 x (message id) characters - it renders both ids, the thread id more often, because the
#: affordance beside it, that affordance's entry in `affordances[]` and both mirror lines each
#: name the thread. The flat part is taken to 420.
#: **Round 29 re-measured this twice, and the second time is the one that counts.**
#:
#: The first re-measurement found it *under* by a flat 225 at every id width: round 27 had
#: measured the record carrying the token-ceiling reason (46 characters) and charged for the
#: host-cap reason too (282). One of the two sentences a record can carry was measured and both
#: were charged for - one shape validated, its peers trusted. It was invisible because
#: `NOT_INCLUDED_SOURCE_CHARS` over-charged by ~500 the other way, and every shape had both.
#:
#: Then the round moved the host-cap explanation to `omission.bound`, stated once, so no record
#: embeds it any more, and bounded every other reason a record can carry. **Certified in
#: `tests/test_omission_sizing_round29.py`** against all six reason variants at id widths of
#: 1, 16, 20 and 30, through the real renderer: the longest (A.9a step 8's, 121 characters)
#: measures 582 at width 16, a flat 486 plus 4.0 per thread-id character and 2.0 per
#: message-id character. Taken to 560, an over-estimate of 74 on the longest variant and more
#: on the rest. A reason that grows past what this bounds fails that test, not a host.
WITHHELD_RECORD_CHARS = 560

#: How many times a withheld record renders the thread its message belongs to. Measured slope
#: 4.0.
WITHHELD_THREAD_ID_COPIES = 4

#: How many times a withheld record renders the message id itself. Measured slope 2.0.
WITHHELD_MESSAGE_ID_COPIES = 2

#: How many times a withheld record whose affordance is a *search* renders the caller's query.
#:
#: **Round 29, R-V01-013(a).** A budget or clock cap (`max_api_calls`, `max_server_ms`, ...)
#: files one record per message in every thread it stopped the server mapping, and the call
#: that raises the cap is the caller's own search, query included. `WITHHELD_RECORD_CHARS`
#: was measured at a six-character query and charged nothing for the query's length, so
#: twenty-four such records were under-charged by 2,458 characters at a 407-character query
#: and by 12,858 at 807. Measured: the query is rendered exactly once per record (in the
#: affordance's `args.query`; the mirror line does not repeat it), so the slope is 1.0 per
#: query character, charged off the query's *JSON-escaped* length. Records whose affordance
#: names a message or a thread render no query and are charged none.
WITHHELD_RECORD_QUERY_COPIES = 1

#: One `not_included_sources[]` entry's characters, before its thread id, on the same inventory
#: as its token twin: the entry, its `why` sentence, its map affordance, that affordance's
#: entry in `affordances[]`, and both mirror lines.
#:
#: **Round 27, R-MCP-024.** This was 700 flat and was the constant that bound after A.9a step 7
#: - which is the step every wide search reaches. Measured off the rendered block itself (the
#: entries, the affordances that name their threads and the mirror lines that name them), one
#: entry costs 846, 901 and 971 characters at thread ids of 5, 16 and 30 characters: a flat 821
#: plus a slope of exactly 5.0 per thread-id character, since the entry, its affordance, that
#: affordance's `affordances[]` twin and both mirror lines each name the thread. Taken to 900
#: and 5, which is an over-estimate of 79 characters at all three lengths.
#: **Round 29, R-MCP-033.** Re-measured after the reason moved to the block. The entry, its
#: map affordance, that affordance's `affordances[]` twin and its mirror line cost 268, 312 and
#: 368 characters at thread ids of 5, 16 and 30: a flat 248 plus a slope of exactly 4.0. Taken
#: to 320 and 4, an over-estimate of 72 at all three lengths - the same margin the withheld
#: constants carry.
#:
#: It was 1,020 + 5T, measured when every entry carried its own copy of the reason. Sixteen
#: split sources cost 17,600 characters of estimate against a 25,000-character cap, which is
#: why a sixteen-thread search returned no mail: the same repetition the withheld records had,
#: in the other block.
NOT_INCLUDED_SOURCE_CHARS = 320

#: How many times a not-included entry renders the thread it is about. Measured slope 4.0.
NOT_INCLUDED_ID_COPIES = 4

#: One not-included **block**'s own characters: the reason, written once, plus the mirror's
#: header line. **Certified in `tests/test_omission_sizing_round29.py`**: with the longest
#: reason a block can carry (the unmappable-thread sentence, 170 characters) the block's own
#: cost measures 434, because the sentence renders twice - once in the block, once in the
#: mirror's header - plus scaffolding. Taken to 510, an over-estimate of 76. Flat, because a
#: block names no thread; its entries do.
NOT_INCLUDED_BLOCK_CHARS = 510

#: One `withheld_groups[]` entry's characters, before its thread id (round 29, R-MCP-033).
#:
#: **Certified in `tests/test_omission_sizing_round29.py`** against every thread-granular
#: reason at id widths of 1, 16, 20 and 30, through the real renderer. The longest
#: (`max_source_threads`, 89 characters) measures 476 at width 16: a flat 412 plus a slope of
#: exactly 4.0 per thread-id character - the entry, its affordance, that affordance's
#: `affordances[]` twin and the mirror line each name the thread. Taken to 490, an
#: over-estimate of 78 on the longest variant.
#:
#: For scale, this is what the round replaces: forty-five messages withheld from three unmapped
#: threads cost `45 x (560 + 4T + 2M)` = 29,520 characters at T = M = 16 as records - more
#: than the whole host cap. The same omission, written at the granularity of the call that
#: undoes it, costs `3 x (490 + 64)` = 1,662.
WITHHELD_GROUP_CHARS = 490

#: How many times a withheld group renders the thread it is about. Measured slope 4.0.
WITHHELD_GROUP_ID_COPIES = 4

#: One `withheld_tail[]` entry's characters, before the query its widening call carries
#: (round 29, R-V01-007). Measured on the real serializer with the longest thread-cap reason
#: and every count at five digits: a flat 465 plus exactly 2.0 per query character (the query
#: renders in the affordance and in its `affordances[]` twin). Taken to 540 and 2. At most
#: one per cap, and only two caps fold, so the whole block is bounded at two entries.
WITHHELD_TAIL_CHARS = 540
WITHHELD_TAIL_QUERY_COPIES = 2
#: Token twin, scaled from the group's the way the group's was scaled from the entry's.
WITHHELD_TAIL_TOKENS = 50

#: One participant record's scaffolding, before its address and its citations.
#: Raised from 150 to 175 in round 31, for `PARTICIPANT_STRUCTURAL_TOKENS`' reason and by the
#: same measurement: the empty record is 175 characters and the address is charged beside it.
PARTICIPANT_STRUCTURAL_CHARS = 175

#: The quoting and separators around one cited message id inside a participant record.
PARTICIPANT_CITATION_CHARS = 6

#: One display-name entry's characters before the name itself: the `Content` object, its two
#: closed-vocabulary values, the fence delimiters and the JSON separators around it.
DISPLAY_NAME_CHARS = 120


def row_chars(
    row_id: str,
    text: str | None,
    *,
    declared: int = 0,
    auth: str = "",
    from_address: str = "",
    from_display: str = "",
) -> int:
    """One disclosed row's characters on the wire, at any depth.

    The text is measured, not estimated: `json.dumps` is the encoder that will encode it, so a
    body full of quotes or newlines - which JSON escaping doubles - is charged what it will
    actually cost rather than what an average body costs.

    `declared` is the row's `reductions[]` and `attachments[]`, measured by
    `declarations_chars` (R-V01-003). Neither was charged before round 29's review, and
    essentially all real mail carries at least one: every `multipart/alternative` message
    declares its unused part, ~340 characters on the wire, so the estimate was under by that
    much per row on ordinary mail and the fixture matrix - plain text throughout - never saw it.
    """
    total = (
        ROW_STRUCTURAL_CHARS
        + ROW_IDENTITY_CHARS
        + ROW_ATTRIBUTION_CHARS
        + ROW_ID_COPIES * len(row_id)
        + declared
    )
    if auth:
        total += AUTH_RECORD_CHARS + len(json.dumps(auth))
    # The `From` address and display name, measured (2026-09-21): the address is a bare
    # string, the name a fenced `Content` object charged like the participant index charges
    # its display names.
    # Each once as JSON and once on the mirror line (2026-09-22); an address carries no
    # whitespace and no character JSON escapes, so its text copy is its own length.
    if from_address:
        total += len(json.dumps(from_address)) + len(from_address)
    if from_display:
        total += ROW_DISPLAY_NAME_CHARS + len(json.dumps(from_display)) + len(from_display)
    if text is None:
        return total
    return total + FENCE_CHARS + len(json.dumps(text)) + len(text)


def request_echo_chars(
    asked_for: AskedFor,
    scan_scope: Sequence[ScanScopeEntry],
    not_tried: Sequence[NotTriedEntry] = (),
    affordances: Sequence[Affordance] = (),
) -> int:
    """What the response's account of the *request* renders to, measured off the blocks.

    R-V01-004. The query is echoed in `asked_for.parsed.terms`, in every `asked_for.dropped[].why`,
    in every executed rung's `scan_scope[].q` and in that entry's widening affordance - eight
    copies of an ordinary query and more when terms repeat - and `RESPONSE_STRUCTURAL_CHARS`
    charged a flat figure whatever the query's length. A 146-character query turned a served
    22,904 into a 26,044 refusal. Both blocks exist before the ladder runs, so they are
    serialised here with the encoder that will serialise them and charged at that size. The
    mirror does not render either, so there is no text-half copy to add.

    R-V01-013(a) widened the inventory to the two other blocks that carry the query and are
    known before the ladder runs: `retrieval_report.not_tried[]`, whose budget entries each
    carry the search that would run the rung, and the top-level `affordances[]` a breached
    cap files (the same search, once). Left uncharged, a 157-character query on a response
    with no evidence at all rendered 424 characters past its estimate.
    """
    return (
        len(json.dumps(asked_for.model_dump(mode="json")))
        + sum(len(json.dumps(entry.model_dump(mode="json"))) + 2 for entry in scan_scope)
        + sum(len(json.dumps(entry.model_dump(mode="json"))) + 2 for entry in not_tried)
        + sum(affordance_echo_chars(entry) for entry in affordances)
    )


def continuation_chars(continuation: Continuation | None) -> int:
    """One `continuations[]` entry as the wire carries it: its JSON, and its mirror line.

    Measured off the object rather than bounded, like `declarations_chars`: the producer holds
    the exact continuation it will emit. The mirror line is `surface.rendering`'s
    `continue <scope>[ of thread <id>]: <n> remaining, next <tool> <compact args>`, and is
    written out here the way the reduction and attachment lines are, so a change to the
    mirror's format is a change to this measure. `None` is no continuation and costs nothing.
    """
    if continuation is None:
        return 0
    dumped = continuation.model_dump(mode="json")
    offer = dumped["affordance"]
    compact = json.dumps(offer["args"], separators=(",", ":"))
    where = f" of thread {continuation.thread_id}" if continuation.thread_id else ""
    line = (
        f"continue {continuation.scope}{where}: {continuation.remaining} remaining, "
        f"next {offer['tool']} {compact}"
    )
    return len(json.dumps(dumped)) + 2 + len(line) + 1


def error_entry_chars(entry: ErrorEntry) -> int:
    """One in-band `errors[]` entry as the wire carries it: its JSON, and its mirror line.

    Measured off the object like `continuation_chars`. The mirror line is
    `surface.rendering`'s `note <code> for <scope>`, written out here so a change to the
    mirror's format is a change to this measure. What a page probe charges for the
    `handle_stale_unverifiable` note a page served through a handle can carry (continuation
    correctness, 2026-09-15): a page is bisected to the boundary, and a note nothing charged
    is the one way a page the estimate admitted could render over the cap.
    """
    line = f"note {entry.code.value} for {entry.scope}"
    return len(json.dumps(entry.model_dump(mode="json"))) + 2 + len(line) + 1


def affordance_echo_chars(affordance: Affordance) -> int:
    """One top-level `affordances[]` entry, serialised as the wire will serialise it, plus its
    separator. What `request_echo_chars` charges a breached cap's call at; a budget-cap record
    is charged its own query copy and the call it shares with its siblings is charged here,
    once (`Builder.add_affordance` lists a call once)."""
    return len(json.dumps(affordance.model_dump(mode="json"))) + 2


def declarations_chars(
    reductions: Sequence[Reduction], attachments: Sequence[AttachmentMetadata]
) -> int:
    """What a row's `reductions[]` and `attachments[]` render to, JSON and mirror lines both.

    Measured, not estimated, in the same spirit as the body text: the row holds the exact
    objects the wire will carry, so each is serialised with the encoder that will serialise it
    and its mirror line is counted at the length the mirror will write. The mirror's
    reduction line is `    reduction <kind> removed <n> chars`; its attachment line is
    `    attachment part <p>: <name> (<mime>, <size> bytes)`.
    """
    total = 0
    for reduction in reductions:
        total += len(json.dumps(reduction.model_dump(mode="json"))) + 2  # ", " between items
        line = f"    reduction {reduction.kind.value} removed {reduction.removed_chars} chars"
        total += len(line) + 1
    for attachment in attachments:
        total += len(json.dumps(attachment.model_dump(mode="json"))) + 2
        total += (
            len(
                f"    attachment part {attachment.part_id}: {attachment.filename} "
                f"({attachment.mime_type}, {attachment.size} bytes)"
            )
            + 1
        )
    if reductions or attachments:
        total += 32  # the two keys and their brackets, once per row that has either
    return total


def source_chars(thread_id: str) -> int:
    """One source's scaffolding, with its thread id measured rather than assumed.

    The id is priced off its own length for the reason `row_chars` prices a message id off
    its own: the fixtures' ids are shorter than Gmail's, and an estimate whose margin depends
    on which of the two it meets is not a bound on the one it was not measured against.
    """
    return SOURCE_STRUCTURAL_CHARS + SOURCE_ID_COPIES * len(thread_id)


def not_included_chars(thread_id_chars: int) -> int:
    """One `not_included_sources[]` **entry**'s characters, off the thread id it names.

    Takes a length rather than the id for the same reason `withheld_chars` does: A.9a step 7's
    own entries know their thread (`Layout.split_off` holds it), but the entries a response
    already carried before the ladder ran are a count, so the caller supplies the widest thread
    id the layout knows about.

    **Round 29 halved this and then some**, by moving the reason out of the entry and into its
    block. The entry, its map affordance, that affordance's `affordances[]` twin and its mirror
    line now measure 268, 312 and 368 characters at thread ids of 5, 16 and 30 - a flat 248
    plus a slope of exactly 4.0 - where the same inventory carrying its own copy of a
    253-character `why` measured 752, 796 and 852. `not_included_block_chars` charges the
    sentence once, where it is now written once.
    """
    return NOT_INCLUDED_SOURCE_CHARS + NOT_INCLUDED_ID_COPIES * thread_id_chars


def not_included_block_chars() -> int:
    """One `not_included_sources[]` block's own characters: the shared reason, said once.

    Flat, because a block names no thread - its entries do. See the constant for the
    certified measurement.
    """
    return NOT_INCLUDED_BLOCK_CHARS


def withheld_group_chars(thread_id_chars: int) -> int:
    """One `withheld_groups[]` entry's characters, off the thread id it names.

    Takes a length rather than the id for the same reason `not_included_chars` does: some of
    the groups a layout charges belong to threads it capped away before the ladder ran and no
    longer holds, so the caller supplies the widest thread id it knows about.
    """
    return WITHHELD_GROUP_CHARS + WITHHELD_GROUP_ID_COPIES * thread_id_chars


def withheld_tail_chars(query_chars: int) -> int:
    """One `withheld_tail[]` entry's characters, off the query its widening call carries."""
    return WITHHELD_TAIL_CHARS + WITHHELD_TAIL_QUERY_COPIES * query_chars


def withheld_chars(message_id: str, thread_id_chars: int, query_chars: int = 0) -> int:
    """One `withheld` record's characters, off both ids it renders and the query if it does.

    `thread_id_chars` is a length rather than the id itself because the layout that charges
    this has, by the time it charges it, sometimes already removed the source the message came
    from - so the caller supplies the widest thread id the layout still knows about, which is
    an upper bound on the one this record will name (every accounted id belongs to a thread the
    layout is either still holding as a source or has recorded in `split_off`).

    `query_chars` is the JSON-escaped length of the query for a record whose affordance is a
    search that carries it (a budget or clock cap's), and zero for every other record
    (R-V01-013(a)).
    """
    return (
        WITHHELD_RECORD_CHARS
        + WITHHELD_THREAD_ID_COPIES * thread_id_chars
        + WITHHELD_MESSAGE_ID_COPIES * len(message_id)
        + WITHHELD_RECORD_QUERY_COPIES * query_chars
    )


def json_string_chars(text: str) -> int:
    """How many characters `text` occupies inside a JSON string, escapes included, no quotes.

    The estimate charges a query off this rather than off `len(text)` because a query with
    quotes or backslashes in it renders longer than it reads, and every block that carries the
    query carries it as a JSON string.
    """
    return len(json.dumps(text)) - 2


def recommended_expansion_chars(hit_ids: Sequence[str], *, limit: int) -> int:
    """The recommended expansion's characters, off the longest `limit` hit ids it could name.

    An over-estimate by construction: it is charged whether or not the response emits one,
    and it prices the longest ids rather than the ones actually chosen.
    """
    longest = sorted((len(message_id) for message_id in hit_ids), reverse=True)[:limit]
    return RECOMMENDED_EXPANSION_CHARS + RECOMMENDED_EXPANSION_ID_COPIES * sum(longest)


def collapsed_run_chars(member_ids: Sequence[str], thread_id: str = "") -> int:
    """One declared collapsed run's characters: its record, the thread id its affordance
    names (twice, counting the search path's twin), and the member ids it lists once."""
    return (
        COLLAPSED_RUN_CHARS
        + COLLAPSED_RUN_THREAD_ID_COPIES * len(thread_id)
        + sum(
            COLLAPSED_RUN_MEMBER_CHARS + COLLAPSED_RUN_MEMBER_ID_COPIES * len(mid)
            for mid in member_ids
        )
    )


def participants_chars(participants: Sequence[ThreadParticipant]) -> int:
    """The participant index's characters, off the same tuple `participants_tokens` prices."""
    return sum(
        PARTICIPANT_STRUCTURAL_CHARS
        + len(entry.address)
        + sum(PARTICIPANT_CITATION_CHARS + len(cited) for cited in citations_of(entry))
        # INJ-05's `{display_name, address}` pair. Measured rather than bounded, for the
        # reason the address and the citations are: this object is holding the exact strings
        # the wire will carry, so there is nothing to estimate.
        + sum(DISPLAY_NAME_CHARS + len(name.text) for name in entry.display_names)
        for entry in participants
    )


def row_tokens(
    text: str | None, *, auth: str = "", from_address: str = "", from_display: str = ""
) -> int:
    """One disclosed row's share of the response, at any depth. A11's rule, once.

    `text is None` is a stub row and still costs its structure: that is the whole of the
    amendment, and it is why a degradation step can no longer make the response larger.

    `auth` is this message's `Authentication-Results` header, when the observation carried
    one. Measured rather than bounded: the header has no length limit, so charging its
    published bound on every row would be a 512-character charge against a field that is
    usually thirty - safe, and large enough to degrade responses that fit.
    """
    structure = ROW_STRUCTURAL_TOKENS + ROW_IDENTITY_TOKENS + ROW_ATTRIBUTION_TOKENS
    if auth:
        structure += AUTH_RECORD_TOKENS + len(auth.split())
    # The name's words, once as JSON and once on the mirror line (2026-09-22). The address is
    # one token in each copy and replaces one - `null`, `none` - that `ROW_ATTRIBUTION_TOKENS`
    # already holds; only an address with whitespace in it would cost more, and none passes
    # `is_an_address`.
    if from_address:
        structure += 2 * max(0, len(from_address.split()) - 1)
    if from_display:
        structure += ROW_DISPLAY_NAME_TOKENS + 2 * len(from_display.split())
    if text is None:
        return structure
    return structure + WIRE_COPIES_OF_DISCLOSED_TEXT * len(text.split())


def collapsed_run_tokens(members: int) -> int:
    """One declared collapsed run's share: its own record, plus the ids it lists.

    A collapsed member is not a row and states no identity block, so this charges the row
    structure alone.
    """
    return ROW_STRUCTURAL_TOKENS + COLLAPSED_RUN_MEMBER_TOKENS * members


def citations_of(participant: ThreadParticipant) -> tuple[str, ...]:
    """Every message this participant record cites, under every role, with repeats.

    With repeats, because each is a separate entry on the wire: an address that authored a
    message and was also addressed on it appears in two lists and is rendered twice.
    """
    return tuple(cited for role in PARTICIPANT_ROLES for cited in getattr(participant, role))


def participants_tokens(participants: Sequence[ThreadParticipant]) -> int:
    """The participant index's share of the response (R-DISC-032).

    Charged off the same tuple the envelope carries and the layout plans, so the ladder's
    number and the envelope's number stay the one number
    `test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number` holds them to.
    """
    return sum(
        PARTICIPANT_STRUCTURAL_TOKENS
        + PARTICIPANT_CITATION_TOKENS * len(citations_of(entry))
        + sum(DISPLAY_NAME_TOKENS + len(name.text.split()) for name in entry.display_names)
        for entry in participants
    )


def measure_tokens(envelope: Envelope) -> int:
    """Whitespace-token estimate of the response this envelope will be sent as.

    This is deliberately **not** presented as the pinned tokenizer of DISC-04/PF-6: that
    tokenizer is registered at G0 and inventing one here would make this estimate the de
    facto bar. It exists so the ceiling can be enforced at all (DISC-06), and it is named
    as an estimate everywhere it is used.

    `disclosure.layout.layout_tokens` computes the same number from the same inventory, and
    `test_the_ladders_measure_and_the_envelopes_measure_are_the_same_number` holds the two
    equal on assembled responses. Two independently-written measures would let the ladder
    believe it had fitted a response the envelope then refuses.
    """
    total = RESPONSE_STRUCTURAL_TOKENS
    for source in envelope.sources:
        for row in source.messages:
            if row.content is None:
                total += row_tokens(None)
                continue
            total += row_tokens(unfence(envelope.fence_nonce, row.content.text))
        total += sum(collapsed_run_tokens(len(run.member_ids)) for run in source.collapsed_runs)
        total += participants_tokens(source.participants) + SOURCE_STRUCTURAL_TOKENS
    return (
        total
        + WITHHELD_RECORD_TOKENS * len(envelope.withheld)
        # R-V01-008: the type-level check had no term for groups and counted not-included
        # *blocks* where the layout counts entries, so it fell below the wire on every grouped
        # response while its two certifying tests, single-source both, passed.
        + WITHHELD_GROUP_TOKENS * len(envelope.withheld_groups)
        + WITHHELD_TAIL_TOKENS * len(envelope.withheld_tail)
        + NOT_INCLUDED_SOURCE_TOKENS * len(envelope.not_included_entries)
    )


def wire_tokens(structured: Any, text: str) -> int:
    """The rendered response, measured. **This is the wire, not an estimate of it.**

    The two things a client receives - the serialised `structuredContent` and the text
    mirror beside it - counted in the same crude whitespace unit `measure_tokens` estimates
    in, so the two numbers are comparable and the claim "the declared ceiling bounds the
    rendered wire" is a measurement rather than a hope. Used by the tests that check the
    ceiling and by nothing on the serving path: measuring the wire requires serialising it,
    and the ladder has to decide before there is anything to serialise.
    """
    return len(json.dumps(structured).split()) + len(text.split())


def rendered_chars(structured: Any, text: str) -> int:
    """**The character measure that did not exist anywhere in this codebase** (R-MCP-021).

    The size of the `CallToolResult` a client is handed, in the unit an MCP host enforces:
    the serialised `structuredContent` plus the text mirror beside it. `grep -rl
    maxResultSizeChars server/src` returned nothing before round 26, and the consequence was
    R-DISC-033: an ordinary twelve-message thread rendered 25,358 characters against the
    host's 25,000-character cap while declaring `truncated_by: null`, `partial: false`,
    `withheld: []` and `included: 12 of 12`. The host cuts what does not fit, above the SDK,
    where nothing in this process can observe it or declare it - so the check has to be on
    this side or it does not exist.

    Both halves are counted because a host counts both: `types.CallToolResult` carries the
    text content and the structured content together, and which of the two a given host
    charges for is not something this server can know. Counting the larger quantity is the
    direction that cannot under-declare.

    This is the wire, not an estimate of it. `disclosure.layout.layout_chars` is the estimate
    the ladder shrinks against, and `test_the_character_estimate_bounds_the_rendered_result`
    holds the estimate above this number over the shape matrix.
    """
    return len(json.dumps(structured)) + len(text)


def degradation_artifacts(envelope: Envelope) -> tuple[str, ...]:
    """Every trace of the A.9a ladder actually having run, read off the payload.

    A response that says `truncated_by: mailweave` is claiming MailWeave shortened it. The
    claim is checked against this enumeration rather than believed: a flag with no
    artifact behind it is a claim about a step that did not happen.
    """
    found: list[str] = []
    for source in envelope.sources:
        if source.collapsed_runs:
            found.append(f"collapsed_run:{source.thread_id}")
        for row in source.messages:
            if row.depth in (Depth.STUB, Depth.SNIPPET):
                found.append(f"depth:{row.id}={row.depth.value}")
            found.extend(
                f"reduction:{row.id}={reduction.kind.value}"
                for reduction in row.reductions
                if reduction.kind is ReductionKind.BODY_HEAD_TRUNCATED
            )
    found.extend(
        f"withheld:{record.id}"
        for record in envelope.withheld
        if record.cap is WithheldCap.DISCLOSED_TOKEN_CEILING
    )
    found.extend(
        f"not_included_source:{entry.thread_id}" for entry in envelope.not_included_entries
    )
    # **Navigation redesign (2026-09-14).** Two more traces of MailWeave having shortened a
    # response: a thread-granular group filed under the ceiling (a scoped or deferred thread
    # of an explicit read), and a `requested` continuation, which exists only because part of
    # the request was cut from this response.
    found.extend(
        f"withheld_group:{group.thread_id}"
        for group in envelope.withheld_groups
        if group.cap is WithheldCap.DISCLOSED_TOKEN_CEILING
    )
    found.extend(
        f"continuation:{continuation.scope}"
        for continuation in envelope.continuations
        if continuation.scope == "requested"
    )
    return tuple(found)
