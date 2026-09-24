# ROUND 29 — the v0.1 closure review (R-MCP-033, R-MCP-039, the three constants)

**Reviewer:** R-V01 (independent, adversarial) · **Date:** 2026-09-09 · **Scope:** the seven
items the owner named — R-MCP-033's nine requirements, R-MCP-039, the certificate invariants,
retry termination, the three sizing constants, the demo document, and §5a on `_exhausted`.
**One question:** is v0.1 ready for live acceptance?

**I did not write this code and I have taken nothing in `IMPLEMENTER.md` as evidence.** Every
number below is off a `CallToolResult` handed back by the shipped `surface.server.call` over the
shipped service and the synthetic transport, or off the A.9a layout captured from the shipped
`run_ladder` on that same call. Where I lifted the host backstop it is said so, and the reason is
to read the rendered size of a response the backstop refused rather than to serve it.

---

## Environment

Working tree `/root/mailweave` (not a git repository; **nothing in it was modified** — the three
files I planted replants into were planted in a scratch copy and `cmp`'d back identical).
`mailweave` resolves to `/root/mailweave/server/src/mailweave/__init__.py` in every probe
(`kit.py` asserts it). Probes: `/tmp/claude-0/-home-claude/575d70c1-c8ad-5ed4-8fc6-31be74875a3b/scratchpad/r29/p1_sweep.py … p16_misc.py`,
logs beside them as `p*.log`. Vocabulary and addresses are the round-26/27 fixtures' own
(`plinth`, `.example`, `.invalid`); no fixture carries real or realistic mail.

**The commanded run:**

```
$ .venv/bin/python -m pytest tests/test_r_mcp_033_round29.py tests/test_r_mcp_039_round29.py \
    tests/test_recovery_chain_round29.py tests/test_omission_sizing_round29.py tests/test_round27.py -q
182 passed, 0 failed, 0 skipped, 0 xfail/xpass   (5.9 s; the conftest suppresses the summary line,
                                                  counted with -rA)
```

Spot-check of the files the diff re-pinned: `test_disclosure_round23 test_round25 test_round26
test_round28 test_mcp_surface_round24 test_field_census test_envelope_serialisation
test_disposition_invariant test_disposition_property` — 349 collected, exit 0. Replants
R123/R124/R125 planted one at a time on a scratch copy: every cited test **FAILED** when planted
(5/5 citations), and passes on the working tree. The full suite was not run.

---

## What was executed, by scope item

### A. R-MCP-033 — the nine requirements

Evidence for each is in the table at the end. Two things the shipped test does not tell you:

* The 18×3 fixture at `max_hit_threads: 3` serves at **21,074** characters with 16 groups, 0
  records, `omission.withheld_messages: 48`, `withheld_by_cap: {max_hit_threads: 45,
  disclosed_token_ceiling: 3}`. But its `affordances[]` block already holds 20 entries of which
  3 are duplicates (`p4_dup.py`): every id A.9a step 7 groups still gets its own
  `affordances[]` twin and its own `next call` mirror line (`assemble.py:1608-1617`). On the
  fixture that is 321 characters; on three 200-message threads it is **31,031** characters of
  `affordances[]` and 403 mirror lines for two groups the estimate charged 1,108 for (R-V01-002).
* Grouping applies only where a thread holds ≥ 2 observed ids (`GROUP_WORTH_WRITING = 2`). On a
  mailbox whose capped-away hit threads are **single messages** the round changes nothing: at
  `max_hit_threads: 1`, 28 such threads serve (18,070 chars), **30 decline** ("carries no mail"),
  35 decline at an estimated 26,694 against a response that would render ≈21,000, and 45 at
  33,254 (`p6_marginal.py`). At the published width the same mailbox declines from 24 threads.
  That is R-MCP-033's own sentence — the bookkeeping crowds out the mail — in the shape the fix
  does not reach (R-V01-007).

### B. R-MCP-039 — `body_full` near the ceiling (`p12_039.py`)

Single-message `body_full` reads at 500, 1,000, 1,400 … 20,000 words; long-token bodies at
600-3,000 words; two, three and five large messages in one call; a `multipart/alternative`
large message. **No `-32603` anywhere.** Every over-cap read declines `budget_exhausted` with
`narrowing: {view, body_full, body_clean}`, and the offered `body_clean` call serves in one hop
(13,819-23,421 chars). The largest unabridged body served was 1,000 words (19,892 chars); 1,400
declined — consistent with `V0_1_DEMO.md` §8's "roughly half the cap".

The same class is **open on the other producer**: `mailweave_thread_map` of a thread with ≥ 420
messages raises `MCPError -32603` ("MailWeave's own response model refused the response
MailWeave built"), and so does the server's own `retry_with` from a search whose top hit sits in
such a thread (R-V01-006).

### C. Certificate and omission invariants (`p11_forge.py`, `p11b_forge.py`)

Against the envelope the service built for the fixture, through `model_copy`, `model_construct`
and a `vars()` write on a `WithheldGroup`: a count edited down, a group dropped, a group
duplicated, a group re-threaded — **all five refused** at the wire (`_withheld_matches_the_
certificate` or the seal). `certify()`'s set-difference assertions are unchanged and the sum
assertion is reached (replant R125 caught). `H == disclosed ∪ withheld` over the original ids
holds on the wire: `18*3 == disclosed + named + Σ message_count` (the shipped test, re-run).

What is **not** checked: `omission`. `model_copy(update={"omission": OmissionSummary(
withheld_messages=0, ...)})` and `omission=None` both **serialise** on an envelope withholding
48 messages. `wire.py:190` says the equality is "asserted at mint time"; it is computed by the
builder and asserted nowhere (R-V01-011). Emptying `affordances[]` also serialises, which is
fine — each group carries its own call — and is why the per-message twins are pure repetition.

### D. Retry termination (`p5_chain.py`, 13 chains through the shipped `call`)

Bounded and cycle-free: no chain exceeded 4 hops, none repeated a `(tool, args)`, every decline
carried `narrowing` and `terminal`. From the published width on 30 single-message threads:
`12 → 6 → 3 → 1 → thread_map{segment: 0}`, four hops, served. Three things are not truthful:

* the retry is not the failed call narrowed on one dimension — it is `{"query", "budget":
  {"max_hit_threads": n}}` and nothing else. A caller's `max_disclosed_tokens: 3000`, `view:
  snippet` and `scan.max_pages: 1` were dropped at hop 1; a `max_disclosed_tokens: 620` decline
  was "recovered" by a retry served at the published 9,000 (R-V01-009);
* `thread_map` of a 400-message thread: `narrowing: segment None → 0`, and `segment: 0` yields the
  identical single 400-member run — the dimension narrowed does not limit; hop 2 is `terminal`
  (R-V01-010);
* `get_messages` of 12 ids across 12 threads at `stub`: `terminal: true`, "no narrower request
  this server can offer would return evidence" — 11 ids serve, and so would any per-thread read
  (R-V01-010).

### E. The three sizing constants

**(1) Completeness of the reason census.** Every `note_withheld(` producer: `assemble.py:366`
(partial-source), `:1608` (step-7 group), `:1624` (step 8), `:1897` (the cap sweep — `max_hit_
threads`, `max_source_threads`, and the budget/clock caps via `BudgetBreach.rendered()`),
`expansion.py:528` (step 8). Every `add_not_included_source(` why: step 7 (both producers) and
`entry.unmappable` (two sentences). All of those sentences are in `WITHHELD_WHYS`/`BLOCK_WHYS`
at their widest fills, **except**: (a) the budget-cap variant's *affordance* — the code writes a
`mailweave_search` carrying the **caller's query** (`policy/budget.py:119-122`, up to
`MAX_QUERY_CHARS = 8,000`), the test certifies a `thread_map{thread_id}`; (b) `BudgetCapName.
MAX_HTTP_REQUESTS` renders as `max_http_requests` (17 chars), the census uses `max_quota_units`
(15); (c) `partial_source_failure` embeds the thread id, so its slope is 5T not 4T, and thread
ids are unbounded on the wire (`Field(min_length=1)`). None of the three breaks the bound at
Gmail's 16-character ids and the demo's 16-character query; (a) does at ~90 query characters.

**(2) Through the real renderer?** Half. The mirror half is `_residue_lines` — real. The JSON
half is `json.dumps(..., separators=(",", ":"))`; `rendered_chars` uses the default separators.
That under-measures every record by 21-25 (`p7_certmethod.py`): the headline "over-estimate of
74 on the longest variant" is **49** on the serializer the host cap is measured with. Still a
bound. The certification also measures one twin per record; it cannot see R-V01-002.

**(3) The existing matrix** — `test_round27::test_the_character_estimate_is_at_or_above_the_
rendered_result`, 19 shapes × 2 tools: **passes**. The smallest served slack in my own sweep is +30 (`thread_map`,
120 messages), one step short of where (4) starts.

**(4) Shapes where the estimate is below the rendered result** (`p1_sweep.py`, 200 shapes;
`p2_causes.py`, `p2b.py`, `p3_breakdown.py` isolate each):

| shape | estimate | rendered | slack | cause |
|---|---:|---:|---:|---|
| `get_messages`, 20 ids across 20 threads, stub | 24,086 | 45,091 | **−21,005** | expansion charges step-7 groups, emits records (R-V01-001) |
| `get_messages`, 12 ids across 12 threads | 24,338 | 26,483 | −2,145 | same; declines `terminal: true` |
| search, 3 threads × 200, one hit each | 19,158 | 55,030 | **−35,872** | one `affordances[]` twin + mirror line per grouped id (R-V01-002) |
| search, 4 threads × 12, 30 senders/30 rcpts | 20,834 | 22,471 | −1,637 | same |
| search, 6 HTML (`multipart/alternative`) threads | 24,300 | 24,944 | −644 | reductions uncharged, ~340 each (R-V01-003) |
| search, 6 threads with an attachment | 24,300 | 25,334 | −1,034 → **refused** | reductions uncharged, ~405 each (R-V01-003) |
| search, 6 threads, 146-char query | 24,300 | 26,044 → **refused** | −1,744 | query rendered 8-22×, flat constant (R-V01-004) |
| `thread_map`, 300 / 400 messages | 19,496 / 24,496 | 21,266 / 27,266 | −1,770 / −2,770 | run members rendered 3×, charged 2× (R-V01-005) |
| `get_messages`, 1 id in a 400-message thread | — | refused `terminal: true` by the backstop | | same |
| token unit: the 18×3 fixture, `measure_tokens` vs `wire_tokens` | 1,547 | 1,786 | −239 | no group term, per-block not per-entry (R-V01-008) |

**Tuned or measured?** Measured. The sequence 420 → 720 → 560 is what re-measuring against the
host-cap sentence and then moving that sentence to `omission.bound` produces; every constant is
above every variant it was certified against, by 49-166 on the real serializer; and the one that
came *down* (`NOT_INCLUDED_SOURCE_CHARS`) came down because the 253-character sentence left the
entry, which I confirmed at 337/entry marginal against 384 charged. Nothing was moved to make
a shape pass. What is wrong is the **inventory**, not the figures: the shapes the constants do not
see (above), and a flat charge at the longest `why` that over-charges the dominant
`max_hit_threads` record by **193** (463 rendered marginal, 656 charged) — which is the arithmetic
behind R-V01-007. A group renders 454 marginal against 554 charged (+100).

### F. The demo document (`docs/V0_1_DEMO.md`, `docs/SETUP.md` §5)

Every command resolves: `mailweave --version` prints `mailweave 0.1.0`; `doctor` and `serve
--client` exist with those flags; the §7 script's imports (`surface.runtime.start(client_path=)`,
`Runtime.service/.close`, `surface.server.call`, `partition.rendered_of`, `measure.rendered_chars`)
are the shipped names; `tool_list()` has exactly the four tools §4 names; the scope is
`gmail.readonly` only. Claims wider than the code: §5's "no `-32603` … no unrecoverable decline"
is not something the code guarantees (R-V01-006, R-V01-005); §7's "the records of those runs are
committed beside this file" — `validation-records/` in this tree holds only
`DEADLINE_DECISION.md`, and neither the two diagnostics `R-MCP-033.md` cites nor the acceptance
record exist; §6's `withheld_threads` is the number of *groups* (three whole threads withheld as
single records → `withheld_threads: 0`).

### G. §5a — is `_exhausted` reachable? **Reachable.**

`mailweave_search {"query": …, "budget": {"max_disclosed_tokens": N}}` with N in [620, ~1,000]
on a mailbox with ≥ 2 hit threads reaches it 15 times in 48 shapes (`p10_exhausted.py`): the
ladder strips every source, tokens still bind (`~730 whitespace tokens against a declared ceiling
of 620`), characters do not, and the message is `_exhausted`'s. Its prose is now wrong for what
it describes — "What is left is 0 row(s), of which 0 are E2 floor membership the ladder may never
remove, and 0 declared collapsed run(s). A floor larger than the overflow ceiling…" about a
response with no floor and no rows — and its retry drops the caller's token budget (R-V01-009).
Not unreachable; keep it and rewrite the sentence off what the layout holds.

---

## Findings

Numbered R-V01-001 onward. Severity per AGENT_LOOP §4; the owner's rule for this round — *an
under-estimate is HIGH* — applied as written. Reachability is mine.

| # | finding | Severity | Reachability |
|---|---|---|---|
| **R-V01-001** | The expansion producer charges A.9a step-7 splits as **groups** and emits them as **records**: `expansion._record_ladder_dispositions` files every `withheld_id` at message granularity while the shared `_split_off` grouped them. `mailweave_get_messages` with ≥ 12 ids across ≥ 12 threads: estimate 24,086-24,938 inside the cap, rendered 26,483-45,091, refused **`terminal: true`**. This is the shape the work order forbade reopening (R-MCP-024's class) | **HIGH** | REACHABLE today, every `get_messages` naming ids from 12+ threads |
| **R-V01-002** | A grouped step-7 id still costs one `affordances[]` entry and one `next call` mirror line each (`assemble.py:1617`, `builder.add_affordance` does not dedupe): 400 grouped ids → 400 identical `thread_map` twins, 31,031 chars, charged 1,108. Three 200-message threads with one hit each: estimate 19,158, rendered 55,030. The fixture itself carries 3 duplicates | **HIGH** | REACHABLE today on any search whose step 7 splits a multi-message source |
| **R-V01-003** | `row_chars` charges nothing for a row's `reductions[]` or `attachments[]`; each reduction renders ~340 (JSON + mirror line), a hidden-content reduction ~405. Six `multipart/alternative` threads: −644; with one attachment row each: 25,334, refused. The fixture matrix never emits HTML (the R-MCP-023 lesson, one layer up) | **HIGH** | REACHABLE-IF-GMAIL, near-certain: essentially all real mail is `multipart/alternative` |
| **R-V01-004** | The query is rendered 8-22× (`asked_for.parsed.terms`, `asked_for.dropped[].why`, every `scan_scope[].q` and its widening affordance) and `RESPONSE_STRUCTURAL_CHARS` is flat. A 146-char query turns a 22,904 response into a 26,044 refusal; `MAX_QUERY_CHARS` is 8,000 | **HIGH** | REACHABLE today, any compound Gmail query of ~100+ characters |
| **R-V01-005** | Collapsed-run members render three times (`member_ids`, the run's affordance, its `affordances[]` twin) and are charged twice: −1,770 at 300 members, −2,770 at 400. Consequences: `thread_map` of a 400-410-message thread declines, its `segment: 0` retry is inert, then `terminal`; **one** message read inside a ≥ 400-message thread is refused `terminal: true` at every view | **HIGH** | REACHABLE-IF-MAILBOX (notification/list threads of 300+); the retry and `terminal` claims are round 29's |
| **R-V01-006** | `mailweave_thread_map` of a thread with ≥ 420 messages reaches the caller as **`-32603`**: step 7's last resort splits the only source, expansion files 420+ records, ROUTE-01 refuses the zero-evidence envelope. `_carries_nothing` gates only layouts with `hit_ids`, which a map has none of. Also reached by following the server's own `retry_with` from a search whose top hit sits in such a thread | **HIGH** | REACHABLE today; the demo's own acceptance line ("no `-32603`") is not met for this shape |
| **R-V01-007** | The single-message-thread form of R-MCP-033 is not fixed. Capped-away threads with one observed id stay per-message records (`GROUP_WORTH_WRITING = 2`) charged 656 against 463 rendered; ≥ 30 such hit threads decline at `max_hit_threads: 1` and ≥ 24 at the published width, while 30-42 would render inside the cap. "A group of one costs more than naming it" is false on the wire (454 vs 463) | **HIGH** | REACHABLE-IF-MAILBOX; a broad `after:` query on a real inbox is exactly this shape, and the live diagnostic's thread multiplicity is not recorded |
| **R-V01-008** | `measure_tokens` (DISC-06's type-level ceiling check) was not updated: no `withheld_groups` term, `not_included_sources` counted per block. On the fixture `measure_tokens` = 1,547 < `wire_tokens` = 1,786, and `layout_tokens` = 2,267 ≠ `measure_tokens`. Round 25's headline property regressed; both tests holding it are single-source (R-MCP-030's shape) and pass | **HIGH** (regression of a PASSed criterion; a test passing for the wrong reason) | REACHABLE today on every grouped response |
| **R-V01-009** | The retry is not the failed call narrowed on one dimension: `narrower_call` mints `{query, budget.max_hit_threads}` and drops `max_disclosed_tokens`, `view`, `scan`, `force_rungs`, `relax`, `structural` and every other budget key. `narrowing` declares one reduction while the retry widens the rest; a `max_disclosed_tokens: 620` decline is "recovered" at 9,000 | MEDIUM | REACHABLE today |
| **R-V01-010** | `terminal`/`narrowing` are untruthful where the schedule has no dimension: `get_messages` at `stub` with 12 ids says final when 11 serve; `thread_map` proposes `segment: 0` on a single-run thread where it changes nothing, then says final. `map_id`+`positions` reads at `body_full` get no `view` hop at all | MEDIUM | REACHABLE today |
| **R-V01-011** | `omission` is an unchecked restatement: a forged `OmissionSummary` (0 withheld on 48) and `omission=None` both serialise. `wire.py:190` claims "asserted at mint time"; `response.py:225-230` still says the block was "deliberately not done" | MEDIUM (honesty) | INERT at the wire today — the builder computes it correctly; in-process only. §5a: defer or take the six-line validator |
| **R-V01-012** | A message whose source left whole under step 7 carries `why: "A.9a step 8: this message could not be carried even as a collapsed-run member…"` — every single-message split on the search path, every split on the expansion path — beside a `not_included_sources[]` block that says step 7 | LOW (honesty) | REACHABLE today |
| **R-V01-013** | The certification's inventory: compact JSON separators (−21..25/record vs the real serializer); the budget-cap variant certified with the wrong affordance (the real one carries the caller's query); `partial_source_failure` slope 5T charged 4T with ids unbounded on the wire; `max_http_requests` two characters longer than the census's cap name | LOW | inert at Gmail widths and the demo query |
| **R-V01-014** | Prose and doc drift: `_exhausted`'s floor-membership sentence on an emptied response (§G); `V0_1_DEMO.md` §7 "records … committed beside this file" against an empty `validation-records/`; `withheld_threads` counts groups; `test_recovery_chain_round29.py`'s docstring names "end-to-end tests below" that are in other files; non-budget declines carry `terminal: false, retry_with: null` | LOW | n/a |

### R-V01-001 — expansion charges groups and emits records

```
ID:            R-V01-001
Severity:      HIGH
Reachability:  REACHABLE today. `mailweave_get_messages` naming ids from twelve or more
               threads, at any view.
Rubric:        DISC-06, MCP-01, I-4; the work order's own rule 4 ("an estimate that charges a
               shape the response does not emit is the defect R-MCP-024 already closed once;
               this must not reopen it").
Location:      server/src/mailweave/surface/expansion.py:523-537 - every `layout.withheld_ids`
                 filed with the default MESSAGE granularity and a per-message affordance;
               server/src/mailweave/disclosure/ladder.py:560-576 - `_split_off` puts the same
                 ids in `grouped_ids` and adds one to `grouped_threads` for both producers;
               server/src/mailweave/disclosure/layout.py:450-454 - charges them as groups.
Repro:         /tmp/.../r29/p4_dup.py (backstop in place) and p2b.py (lifted):
                 n=11: served  est=24,508 rendered=24,138  withheld=3  groups=0  (layout: 1 group)
                 n=12: DECLINED est=24,338 rendered=26,483 terminal=True retry=None
                 n=20: DECLINED est=24,086 rendered=45,091 terminal=True retry=None
               At n=20 the layout says grouped_threads=18, grouped_ids=54; the wire carries 54
               records and 0 groups.
Expected:      layout_chars >= rendered_chars; the decline, if any, narrows rather than ends.
Actual:        under by up to 21,005; a final refusal for a call that serves at eleven ids.
Required fix:  file grouped ids at THREAD granularity in `expansion._record_ladder_dispositions`
               exactly as `assemble.py:1599-1617` does (its docstring already claims "exactly as
               assemble files them"), and add multi-thread `get_messages` shapes to the
               estimate matrix - it is single-thread on every row today.
```

### R-V01-002 — one affordance twin per grouped message

```
ID:            R-V01-002
Severity:      HIGH
Reachability:  REACHABLE today on any search where step 7 splits a source with >= 2 messages.
Rubric:        DISC-06, R-MCP-033 requirement 1 (compact bookkeeping).
Location:      server/src/mailweave/retrieval/assemble.py:1608-1617 - `builder.add_affordance(
                 affordance)` inside the per-message loop for grouped ids;
               server/src/mailweave/envelope/builder.py:121 - `add_affordance` appends, never
                 dedupes;
               server/src/mailweave/envelope/measure.py:320 - `WITHHELD_GROUP_CHARS` prices one
                 twin per group.
Repro:         p3_breakdown.py "F three threads p200 matching=1": affordances[] = 31,031 chars
               (403 entries, 400 of them `thread_map` calls to the two split threads), 403 `next call`
               mirror lines = 12,493 chars; estimate 19,158, rendered 55,030.
               p4_dup.py on the shipped fixture: 20 affordances, 17 distinct.
Expected:      one recovery call per group, charged once.
Actual:        ~110 characters per grouped message, uncharged.
Required fix:  add the thread-map affordance once per split thread (it is already added at
               :1594 for the not-included entry); a builder that refuses a duplicate affordance
               would make the next producer inherit the rule.
```

### R-V01-003 — reductions and attachments are uncharged

```
ID:            R-V01-003
Severity:      HIGH
Reachability:  REACHABLE-IF-GMAIL, near-certain. Every `multipart/alternative` message emits an
               `alternative_part_unused` reduction (round 27 made that shape serve; it never
               made it *measured*).
Rubric:        DISC-06, R-MCP-024's inequality.
Location:      server/src/mailweave/envelope/measure.py:332-342 `row_chars` - id, structure,
                 text; nothing for `MessageRow.reductions` or `.attachments`;
               server/src/mailweave/disclosure/layout.py:176-183 - `PlannedRow.chars()`, which
                 holds `base_reductions` and does not price them.
Repro:         p2_causes.py: per row, plain -> HTML alternative: +340 rendered, +0 estimate;
               plain -> attachment (hidden-content reduction): +405 rendered, +0 estimate.
               6 HTML threads: est 24,300 rendered 24,944 (served, 56 from the cap);
               6 threads with an attachment each: rendered 25,334 -> HostCapExceeded, refused.
Expected:      layout_chars >= rendered_chars on ordinary mail.
Actual:        under by 340-405 per row per reduction; the real-mail slack is negative.
Required fix:  charge `len(json.dumps(reduction.model_dump()))` + its mirror line per
               reduction off `base_reductions` (the layout holds them), and the attachment
               block likewise; add `html_alternative=True` and `has_attachment=True` rows to
               `multi_thread_mailbox` so the matrix stops being plain-text only.
```

### R-V01-004 — the query is rendered many times and charged once, flat

```
ID:            R-V01-004
Severity:      HIGH
Reachability:  REACHABLE today. Any query of roughly 100+ characters on a search that was
               already near the cap - a compound Gmail query is that long.
Location:      server/src/mailweave/envelope/measure.py:168 `RESPONSE_STRUCTURAL_CHARS = 2_600`
                 (flat); the copies: `asked_for.parsed.terms[]`, `asked_for.dropped[].why`,
                 `retrieval_report.scan_scope[].q` and `.affordance.args.query` per executed
                 rung/page.
Repro:         p9_query.py: 136-char query -> 8 copies in structuredContent (paths listed in
               p9.log); 6 threads: qlen 7 -> served 22,904; qlen 146 -> refused at 26,044;
               qlen 286 -> 29,184; qlen 1,126 -> 48,024 (all refused by the backstop).
Expected:      the estimate charges what the response carries.
Actual:        ~8x the query length uncharged on every search; up to 22x when terms repeat.
Required fix:  charge the query off its length times the copies the report will carry (the
               layout is built after the scan scope exists), or bound the copies.
```

### R-V01-005 / R-V01-006 — very long threads: inert retry, false `terminal`, and `-32603`

```
ID:            R-V01-005, R-V01-006
Severity:      HIGH, HIGH
Reachability:  REACHABLE. 300 messages: served, under-estimated by 1,770; 400-410: refused
               with an inert `segment: 0` retry then `terminal: true`; >= 420: `-32603` from `thread_map`, and from a search's own
               `retry_with` when its top hit sits in such a thread (p5_chain.py D8).
Location:      server/src/mailweave/envelope/measure.py:230 `COLLAPSED_RUN_MEMBER_CHARS = 18`
                 + 2 x id - the `affordances[]` twin of the run's `get_messages` call is a
                 third copy (p3_breakdown.py "D thread_map p300": collapsed_runs 12,185 +
                 affordances 6,082 against 15,400 charged);
               server/src/mailweave/disclosure/ladder.py:1007-1033 `_carries_nothing` -
                 `bool(working.hit_ids)` is False for every expansion layout, so an emptied
                 map is returned rather than refused, and `Envelope._no_bare_empty_response`
                 refuses it as ROUTE-01 -> `ValidationError` -> `-32603` at server.py:214.
Repro:         p13_bigthread.py:
                 thread_map p400/p410: declined, retry segment:0, then terminal
                 thread_map p420..p450: *** MCPError -32603
                 get_messages 1 id in a thread of 400/450/600/1000, stub or body_clean:
                   declined terminal=True retry=null
                 search, one hit in a 450-message thread -> retry thread_map -> -32603
Expected:      the evidence, or a truthful, executable decline; never -32603 (R-MCP-039's own
               sentence, and V0_1_DEMO.md §5's acceptance line).
Actual:        that, on the second producer.
Required fix:  price the third copy; an emptiness gate for expansion layouts (`accounted_ids`
               non-empty, `present_ids` empty); a `thread_map` retry that narrows on a
               dimension that exists (a positional slice), and a `get_messages` retry that
               halves `message_ids` before declaring the chain final.
```

### R-V01-007 — the single-message-thread form of R-MCP-033

```
ID:            R-V01-007
Severity:      HIGH
Reachability:  REACHABLE-IF-MAILBOX. A broad `after:` query over a real inbox hits dozens of
               one-message threads. The live diagnostic recorded 45 records, not how many
               threads they came from; `IMPLEMENTER.md`'s "18 threads x 3" is the fixture.
Rubric:        R-MCP-033 requirements 1, 3, 6.
Location:      server/src/mailweave/constants.py:156 `GROUP_WORTH_WRITING = 2`;
               server/src/mailweave/envelope/measure.py:264 - one flat charge at the 121-char
                 step-8 sentence for a record whose `why` is 55 characters.
Repro:         p6_marginal.py, single-message hit threads, `max_hit_threads: 1`:
                 n=28 served 18,070 (27 records) | n=30 DECLINED "carries no mail" |
                 n=35 DECLINED est ~26,694 | n=45 DECLINED est ~33,254
               published width: n=20 served 20,052 | n=24 DECLINED "carries no mail"
               marginal cost per record: rendered 463, charged 656; per group: 454 vs 554.
Expected:      requirement 6 - non-empty evidence inside 25,000 on the broad capped query.
Actual:        the response that would render ~19-21k is refused on its estimate from 30
               threads; from ~42 the true cost of the records alone exceeds the cap.
Required fix:  charge a record off the `why` the ledger already holds for it (the cap notes
               are filed before the ladder runs), and write a capped-away one-message thread as
               a thread-granular entry - the wire shows a group is not dearer than a record.
               Then re-run p6 to the 45-thread mark; if it still declines, R-MCP-033 needs the
               summarised tail round 27 named as its third route out.
```

### R-V01-008 — `measure_tokens` was not moved with `layout_tokens`

```
ID:            R-V01-008
Severity:      HIGH  (a regression of round 25's PASSed property; the certifying tests pass
               because every shape they hold is single-source)
Reachability:  REACHABLE today on every response carrying a group or a not-included block.
Location:      server/src/mailweave/envelope/measure.py:495-499 - `WITHHELD_RECORD_TOKENS *
                 len(envelope.withheld) + NOT_INCLUDED_SOURCE_TOKENS * len(envelope.
                 not_included_sources)`: no `withheld_groups` term, and `not_included_sources`
                 is a tuple of *blocks* since round 29;
               server/src/mailweave/disclosure/layout.py:413-419 - the ladder's number, which
                 does charge both.
Repro:         p15_tokens.py:
                 fixture 18x3 cap 3: layout_tokens=2,267 measure_tokens=1,547 wire_tokens=1,786
                 t12xp3:             layout_tokens=2,660 measure_tokens=1,815 wire_tokens=1,954
               test_disclosure_round23::..._are_the_same_number and test_round25::
               test_the_estimate_is_an_upper_bound_on_the_rendered_wire both pass - one
               thread, no groups, no blocks, on every row of both.
Expected:      `measure_tokens(envelope) == layout_tokens(layout)` and `>= wire_tokens`.
Actual:        neither.
Required fix:  add `WITHHELD_GROUP_TOKENS * len(withheld_groups)` and count
               `not_included_entries`; put one grouped multi-source shape into each of the two
               tests so the next divergence fails.
```

*(R-V01-009..014 are stated in the table and evidenced in §D, §C, §E(2), §F and §G; each names
its file and probe there.)*

---

## The nine requirements of R-MCP-033

| # | requirement | verdict | evidence |
|---|---|---|---|
| 1 | compact bookkeeping, truthful aggregates | **FAIL** as a class; PASS on multi-message threads | 16 groups with exact counts on the fixture, forgeries refused (§C). Not compact where threads hold one message (R-V01-007) and not compact in `affordances[]` (R-V01-002) |
| 2 | counts machine-readable | **PASS** (with R-V01-011 open) | `omission.{withheld_messages, withheld_by_cap, withheld_threads, not_included_sources, bound}` on the served envelope, agreeing with the records on every shape probed; not derived/checked |
| 3 | `max_hit_threads` genuinely reduces the response | **PASS** on the fixture | 18×3 at cap 12 → 6 → 3 → 1 renders 22,689 → 21,464 → 21,074 → 15,373 (2/3/2/1 sources); the shipped strict chain passes. Not monotone in general: 4×3 at cap 12 is 20,178 and at cap 3 is 23,095; 6×3 at cap 6 is 23,262 and at cap 3 is 23,625 — the cap bounds what is *mapped*, and the ladder spends the freed room on depth |
| 4 | never a `retry_with` identical to the failed request | **PASS** | guard + property test; 13 executed chains, no repeat |
| 5 | following the retry produces progress | **FAIL** | bounded (≤ 4 hops) and terminating on every chain, but not truthfully: other dimensions widened (R-V01-009), an inert `segment: 0` (R-V01-010), a false `terminal` (R-V01-010), one retry ending in `-32603` (R-V01-006) |
| 6 | non-empty evidence within 25,000 for this broad capped query | **FAIL** conditional | PASS on the 18×3 fixture (21,074 chars, sources ≥ 1, matched ≥ 1); FAIL from 30 single-message hit threads (R-V01-007) and on 6+ HTML/attachment threads (R-V01-003) |
| 7 | no silent drop | **PASS** | `certify()` unchanged; the sum assertion and the wire-level group comparison refuse edits, drops, duplicates, re-threading; `H == disclosed ∪ withheld` over the original ids on the wire; R125 caught |
| 8 | 45-record regression + independent review | **PASS** for the fixture and this review; the pre-fix failure at `5e86229` is the implementer's claim — this tree has no git history to reproduce it | replants R123/R124/R125 each caught by every citation |
| 9 | live diagnostic repeated | **NOT DONE** | owner's action; no record in `validation-records/` |

**R-MCP-039:** holds for `mailweave_get_messages` at `body_full` on every shape I could build
(§B) — the evidence or an executable `body_clean` decline, never `-32603`. The identical failure
class stands open on `mailweave_thread_map` at ≥ 420 messages and on the search retry that lands
there (R-V01-006); R-MCP-039 as filed is closed, its sentence is not.

**The three constants:** measured, not tuned — every figure is above every variant it was
certified against (49-166 on the real serializer), and the one lowered was lowered because a
253-character sentence left the entry. The certification is incomplete rather than wrong:
compact separators, a wrong affordance on the budget-cap variant, and — the part that matters —
an inventory that cannot see reductions, attachments, the query, the run twin, the per-message
affordance twins, or the expansion producer's records, so `layout_chars >= rendered_chars` is
false on ordinary real mail and every multi-thread `get_messages`. And the flat charge at the
longest sentence over-charges the dominant record by 193, which is why the one-message-thread
shape still declines.

**Verdict:** **v0.1 is not ready for live acceptance.** The fixture shape that broke on 2026-09-08
is fixed and provably accounted for; what blocks is that the estimate the whole design rests on
is below the rendered result on the shapes a real mailbox sends (HTML, attachments, compound
queries, long threads, and every step-7 split), one of those routes ends in `-32603`, and the
broad query is still refused where its hit threads are single messages. Fix R-V01-001/002/003/
008 (all four are round-29 inventory, not new design), gate R-V01-006, then run requirement 9.

---

## Recheck of the repairs (2026-09-09, same reviewer, same probes)

The coordinator named `/home/claude/mailweave`; that path does not exist on this machine. The
repaired files are in `/root/mailweave` (17 source and 15 test files newer than this review,
carrying `WithheldTail`, `evidence_is_the_map`, `request_echo_chars`, `declarations_chars`),
and the recheck ran there. The commanded five files: **211 passed, 1 skipped** (the skip is the
collapsed-run certification's own "more members than distinct ids of this width"). The 200-shape
sweep (`p1_sweep.py`): **no under-estimate, no over-cap, no decline with an estimate inside the
cap**; worst served slack +1,218. Width matrix (`p17_widths.py`): every emitted variant I can
produce — `max_hit_threads` groups + tail, step-7 groups (search and expansion), step-7 singles,
step-8/runs, `get_messages` across 15 threads, `thread_map` 300, budget-cap records under
`max_api_calls` / `max_http_requests` / `max_quota_units` — at thread/message id widths
5/16/20/30/40: all positive, worst +2,026. Tail boundary (`p6b_tail.py`): 23/24/25 threads
serve as 22/23/24 groups; 26 → 24 groups + tail(1); 30/45/60/100 → 24 groups + tail(5/20/35/75),
slack +3,700 throughout; group marginal 453 rendered vs 554 charged; a group of one is written as
a group.

| finding | verdict | evidence |
|---|---|---|
| R-V01-001 | **REPAIRED** | `get_messages` 12-20 ids across threads: served, layout `grouped_threads` == wire groups (4..19), slack +3,500..+5,900; 30 ids: declines with `message_ids 30 → 15`, then serves |
| R-V01-002 | **REPAIRED** | fixture: 17 affordances, 17 distinct; 3×200 one-hit: est 22,369 vs rendered 11,851 (was 55,030) |
| R-V01-003 | **REPAIRED** | 6 HTML threads +2,121; 6 attachment threads +2,121 (both were negative / refused); `declarations_chars` measures the objects the row holds |
| R-V01-004 | **REPAIRED for the request echo; residual** | unique-term 426-char query: est 17,656 vs 15,025. Residual: a row's `reason` re-renders every *matched* term twice (JSON + mirror line) and is uncharged — `plinth`×60 query, 6 threads: backstop refusal at 26,013 (declared, not truncated). MEDIUM, reachable only with many matched terms per row |
| R-V01-005 | **REPAIRED (estimate); capability moved** | run member: 60 rendered vs 64 charged per member; `thread_map` 300 slack +2,670. A single `body_clean` read inside a 300-message thread now declines `terminal` where it served at 23,250 (the true cost is the map skeleton); the documented limit says "≥ ~450". MEDIUM note |
| R-V01-006 | **REPAIRED** | `thread_map` 400-600: declined `terminal: true`, no `-32603`; search → map retry into a 450/600-message thread: declined terminal; 039 sweep (88 lines): zero exceptions |
| R-V01-007 | **REPAIRED at the capped width; residual at the published width** | 26-100 single-message threads at `max_hit_threads: 1` serve with matched mail (16,915-16,946 chars). At the published width ≥ 26 such threads still decline once ("carries no mail") and serve at the first hop (`6`); the demo's §4 smoke test would decline on such a mailbox. LOW note |
| R-V01-008 | **REPAIRED** | fixture: `layout_tokens` = `measure_tokens` = 2,267 ≥ `wire_tokens` 1,764; t8×1, t20×1, t12×3 likewise equal and above the wire |
| R-V01-009 | **REPAIRED** | `max_disclosed_tokens: 620` decline retries with `{max_disclosed_tokens: 620, max_hit_threads: 1}`; D1's `view`/`scan` shape now serves at hop 0 |
| R-V01-010 | **PARTIALLY REPAIRED** | `get_messages` 12/30 ids: `message_ids` halves (12→6, 30→15), chain serves in 2 hops; `thread_map` no longer mints an inert `segment: 0` (unsegmented → terminal). **Not repaired:** `get_messages` by `map_id`+`positions` at `body_full` still declines `terminal: true` with no `view` hop (`recovery.py:163` is gated on `message_ids`); executed on the 3,500-word fixture. The claim "view hop present for map_id+positions" is false |
| R-V01-011 | **REPAIRED** | forged `omission` (0 on 48) and `omission=None` both refused by `_the_omission_summary_restates_the_certificate_exactly`; group edits/drops/duplicates/re-threading still refused |
| R-V01-013 (a) | **NOT REPAIRED — now the one remaining under-estimate** | the budget-cap record's affordance is a `mailweave_search` carrying the caller's query; `withheld_chars` takes no query length and the census still certifies it with a `thread_map` affordance (test line 76 + the tool rule). 12×2 under `max_api_calls: 3` (24 records): slack +7,886 at a 6-char query, +2,608 at 209, **−2,852 at 419, −13,772 at 839**. `max_server_ms` — the cap that bound on the live mailbox — files the same records. HIGH by the owner's rule, reachable with a ~175+ character query on 45 deadline-capped messages; the demo query is 16 characters |

**The constants, re-examined.** `WITHHELD_GROUP_CHARS = 490 (+4T)`: 453 served marginal vs 554
charged at T=16 — measured, +101. `COLLAPSED_RUN_MEMBER_CHARS = 16` at 3 id copies: 60.0 vs 64.0
per member — measured, +4. `WITHHELD_TAIL_CHARS = 540 (+2 query copies)`: holds at 1..1,000
query characters in the certification and end-to-end at 6/209/419 (+3,737/+2,925/+2,085).
`NOT_INCLUDED_*` unchanged and still 337 vs 384 per entry. `WITHHELD_RECORD_CHARS = 560`
now covers only budget-cap and partial-source records: budget-cap marginal is **364** against
656 charged (+292) at a short query — the over-charge is the same longest-variant flat figure as
before, and it is what hides the query copy up to ~175 characters. `measure_tokens` now equals
`layout_tokens` on every grouped shape. None of the figures moved to make a shape pass; the one
hole is an inventory hole (013a), not a tuned number.

**One-line notes, not chased:** (i) MEDIUM — `get_messages` of 20 named ids in a 20-message
thread at `stub` now collapses all 20 named rows into one run (rendered 5,203, `rows=0`) because
the corrected estimate is 25,611 for a response that rendered 21,878 before; the expansion ladder
collapses the *named* rows first. (ii) MEDIUM — row `reason` carries the matched query terms
twice, uncharged (R-V01-004 residual). (iii) LOW — `_exhausted` is still reachable (13/48
shapes) and still says "0 row(s), of which 0 are E2 floor membership" about an emptied response.
(iv) LOW — non-budget declines still carry `terminal: false, retry_with: null`.

## After the recheck (implementer, 2026-09-09)

The two items the recheck left open were fixed in the same pass and are held by tests and
replants; the full suite (3,094 passed, 2 skipped), `ruff`, `ruff format`, `mypy --strict`
and the guards are green on the tree this note is committed with.

* **R-V01-013(a)** — the one remaining under-estimate. `Layout.query_bearing_ids` (seeded from
  the same ledger sweep that files the budget-cap records) charges each such record
  `json_string_chars(query)` on top of `WITHHELD_RECORD_CHARS`; `request_echo_chars` also
  measures `retrieval_report.not_tried[]` and the breached cap's `affordances[]` entry, which
  carry the query and were the reason the zero-record `max_server_ms` shape was 424 under at
  157 query characters. The census now certifies the budget-cap variant with the search
  affordance it really carries, at query lengths 1 / 16 / 300 / 830-with-escapes, and the
  shipped path holds it end to end on both shapes
  (`test_budget_cap_shapes_are_estimated_at_or_above_what_they_render_at_any_query_length`).
  Replant R126. The reviewer's `p17_widths.py` re-run after the fix: no under-estimate, worst
  slack +2,493.
* **R-V01-010, the `map_id` + `positions` form** — the schedule now keys on whichever of
  `message_ids` / `positions` the read used; the `view` hop is offered at `body_full` and the
  positions halve from at most 50 (`test_a_read_by_map_id_and_positions_gets_the_same_view_hop`,
  through a served map's real handle). Replant R127.
* One consequence of charging the report echo: `tests/test_round28.py`'s twelve-message
  recommendation fixture sat 505 characters past the cap at A.9a step 3 once the ~470
  characters of `not_tried[]` were paid for (the rendered step-3 response was 23,404, inside
  the cap - the estimate erring high at the edge), so step 5 collapsed the stubs and no row was
  left for the recommendation to name. The fixture is eleven messages, 657 under, with the
  measurement recorded beside the constant. `RESPONSE_STRUCTURAL_CHARS = 2,600` was *not*
  lowered to rescue it: the flat blocks it covers measure 1,100-1,500 on every shape probed,
  but an inventory of their widest forms (`omission.bound`, every cap name in
  `budget_caps_hit`, every rung in `rungs[]`, `errors[]` declarations, `truncated_by`) comes to
  roughly 2,250, and 350 would not have rescued the fixture in any case. Recorded as a
  precision item, not a bound defect.
* `tests/test_mcp_surface_round24.py`'s matrix gained `search_budget_cut_mid_map`
  (`max_api_calls: 16` over the over-the-cap query: two threads mapped, two cut, records and
  groups beside sources) because after round 29 no shape in it carried a per-message record and
  replant R85 - the mirror dropping `withheld[]` - had silently stopped being caught.
