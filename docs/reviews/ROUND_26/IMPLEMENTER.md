# ROUND 26 — implementer report

**Scope:** the eight findings `docs/reviews/ROUND_26/WORK_ORDER.md` names, under **OD-7**. Nothing
else was fixed. Twelve tracked findings are untouched. What I found beyond the eight is filed at
the end and left.

**Every reproduction was run before anything changed.** All eight reproduced on this tree:
`/tmp/rdisc25/r06_re_prefix.py`, `r08_root_message.py`, `r04_hit_ranks.py`, `r12_unmeasured.py`,
`r15_mcp_wire.py`; `/tmp/rmcp25/p3_filename.py`, `p4_token.py`, `p6_hostcap.py`. Each is re-run
below, unmodified, against the repaired tree.

---

## Part 1 — the thesis, undone by two characters (R-DISC-031, R-DISC-034)

### What changed

* `query/analysis.py`: `REPLY_PREFIXES` (a published, closed set of seventeen reply and forward
  markers) and `strip_reply_prefixes`, which removes leading markers and nothing else. It is a
  **comparison form, not a disclosure form**: no wire field, no row reason and no published score
  passes through it, and `content_tokens` is unchanged, so a caller searching for `re` still finds it.
* `disclosure/weights.py`: `fact_values` tokenises `strip_reply_prefixes(candidate.subject)` for
  the `SUBJECT` fact **and nowhere else**, which is the narrow repair R-DISC scoped.
* `disclosure/weights.py`: A11's two guards — the discriminating-facts narrowing and the
  all-or-none sweep — moved into one function, `a11_scores`. `rank` filters and sorts its output;
  `plan.hit_ranks` maps it to `anchored_value`. One rule, one place, so a third pool inherits both
  halves rather than half of them.
* `tests/test_disclosure_round23.py`: `shared_subject_thread` now carries `S` on the root and
  `Re: S` on every reply. Round 25's version named the prefix in prose and wrote
  `dict.fromkeys(order, subject)`.

### The DISC-01 numbers on the `Re:`-prefixed fixture

`shared_subject_thread(messages=24)`, five single-term queries, ten pairs, at five hit placements.
"Before" is this tree with `strip_reply_prefixes` neutralised, so the two rows differ in exactly the
fix:

| hits at | before: differing pairs | before: \|fill\| per query | after: differing pairs | after: \|fill\| per query |
|---|---|---|---|---|
| (1, 9, 17) | **0 / 10** | 0, 0, 0, 0, 0 | **10 / 10** | 9, 7, 7, 12, 12 |
| (2, 10, 18) | **0 / 10** | 0, 0, 0, 0, 0 | **10 / 10** | 12, 7, 7, 9, 12 |
| (3, 11, 19) | **0 / 10** | 0, 0, 0, 0, 0 | **10 / 10** | 9, 7, 7, 9, 12 |
| (4, 12, 20) | **0 / 10** | 0, 0, 0, 0, 0 | **10 / 10** | 12, 7, 7, 12, 9 |
| (0, 8, 16) | 10 / 10 | 12, 7, 7, 12, 12 | 10 / 10 | 12, 7, 7, 12, 12 |

The last row is why round 25's 15/15 was true and established nothing: at that placement the root is
a *hit*, so the prefix's effect lands in the hit pool and the fill is unaffected. The test this round
adds uses a placement where the root is a **candidate**.

`hit_ranks`, on a pool where the narrowing survives and the component still fires on every hit
(twelve hits, distinct snippets, all carrying the term):

```
BEFORE  distinct anchored values = [4]     -> position is the whole selection (oldest-K)
AFTER   distinct anchored values = [0]     -> a stated zero, and position decides for a stated reason
```

The control in the same test: with the term in half the snippets, `hit_ranks` returns two distinct
values, so the sweep is not "remove everything".

### What each test establishes

| test | what it establishes |
|---|---|
| `test_a_reply_prefix_is_not_a_message_discriminating_fact` | `S` / `Re: S` are one subject to A11 — **and** genuinely different subjects still separate, so this is a repair and not a removal |
| `test_the_reply_prefix_stripper_takes_the_markers_and_nothing_else` | `budget: q3` is untouched; `Re[2]:`, `Fwd: Re:` and `AW:` are; `re` is still a content token elsewhere |
| `test_five_queries_over_a_gmail_shaped_thread_produce_different_fills` | DISC-01's acceptance on the shape Gmail sends, at a placement where the defect was live: 10 of 10 pairs differ and no fill is empty |
| `test_the_reply_prefix_changes_nothing_about_what_is_disclosed` | the stronger statement: the two characters have **no** effect on fill or on `hit_ranks` |
| `test_hit_ranks_applies_the_all_or_none_sweep_that_rank_applies` | the sweep, with a hand-written oracle naming which candidates score above zero |
| `test_hit_ranks_on_gmail_shape_is_a_stated_zero_and_not_a_uniform_nonzero` | through the shipped planner, on a fixture built so the narrowing alone cannot carry it |

### What I could not establish

**The end-to-end probe R-DISC used for R-DISC-031(b) still shows 0 of 10, and A11 cannot reach it.**
`/tmp/rdisc25/r04_hit_ranks.py` drives five queries over a 24-message thread where every message is a
hit and reports "protected top-10 == the 10 EARLIEST by position: True" for all five. That is
**not** `hit_ranks`. The depth map there is decided by which bodies the *retrieval* ladder fetched:
`retrieval/ladder.py::_fetch_bodies(run, sorted(run.evidence_ids), cap=MAX_BODY_FETCHES_L1)` fetches
the first ten ids in **sorted-id order**, and `plan.depth_for` can only return `body_clean` where a
body exists. On a chronologically-named thread that is the ten earliest, for every query. Filed
below as new; it is in `retrieval/`, outside the eight, and I left it.

---

## Part 2 — the host cap (R-DISC-032, R-DISC-033, R-MCP-020, R-MCP-021)

### What changed

**A character measure now exists.**

* `constants.HOST_RESULT_CHAR_CAP = 25_000`, published beside the two token ceilings, with the
  reason the server has to hold the figure itself: the cut happens above the SDK.
* `envelope/measure.rendered_chars(structured, text)` — **the wire, not an estimate**: the size of
  the `CallToolResult` a client is handed.
* `disclosure/layout.layout_chars` — the estimate the ladder shrinks against, priced off the same
  inventory as `layout_tokens`, with the text, the participant addresses and every message id
  **measured** rather than guessed at and only the JSON scaffolding as constants.

**The ceiling is applied at the surface, and the ladder is the mechanism.**

* `Ceilings` gains `host_chars: int | None`. `None` for a layout nobody serves — the harness' arm
  comparison, DISC-04's ratio, every measurement — so a cap that is a fact about the *host* does not
  distort a measurement. `surface/service.SERVED_CEILINGS` sets it on all four tools, which is every
  path by which a response reaches a client.
* `ladder.over_budget` is the fit test in both units, and it is used by the driver, by
  `_degrade_band` (steps 1, 3, 4), by step 7's split loop and by step 8's withholding loop. The
  published precedence is unchanged; the same rungs run for one more reason.
* `assert_cost_did_not_rise` gains a `bounds` argument: a step may raise the token count only where
  the character cap is what is binding and it lowered characters. With no character cap it is byte
  for byte the round-25 gate.
* `surface/partition.declared_result` measures the rendered result against the constant **whatever
  was planned** and raises `HostCapExceeded`; `surface/server.call` turns that into a declared
  `budget_exhausted` refusal with an executable narrower retry.

**`measure_tokens` charges what it had not been charging** (R-DISC-032, and its own rule applied
past the field R-DISC names):

| charge | value | why it was invisible |
|---|---|---|
| `PARTICIPANT_STRUCTURAL_TOKENS` | 15 | the field that was 82 % of a 400-sender response |
| `PARTICIPANT_CITATION_TOKENS` | 1 | one entry per cited message, with repeats across roles |
| `SOURCE_STRUCTURAL_TOKENS` | 60 | a `Source` was worth nothing, so A.9a step 7 — whose job is to remove one — could see no saving in removing one |
| `NOT_INCLUDED_SOURCE_TOKENS` | 55 | one entry per source step 7 splits off, plus its affordance |

The participant figure is exact, not fitted: 2, 13, 31 and 68 participants over 24, 24, 60 and 540
citations reproduce the rendered block to the token, because an address cannot contain whitespace.

**`layout.cost() == measure_tokens(envelope)` survives.** The participant charge is the one that
could have broken it, because the envelope emits the index *narrowed* to the rows it carries. There
is now one narrowing rule — `envelope.wire.participants_within` — called by `PlannedSource.cost`,
by `assemble` and by `expand`. Two consequences worth naming: the search path never narrowed at all
(a step-8 withholding would have been a `ValidationError` waiting to happen), and both paths now
narrow to the source's **rows**, which is the rule `assemble.structure_block` already uses for
`linked`/`unlinked` and for the same reason.

**The claims were corrected** (R-MCP-020): the three `Claim`s in `surface/tools.py` and `SETUP.md`
§6 now say a response never exceeds **either** ceiling it is held to, name the character cap, and
say that a response which cannot be brought inside is refused with a narrower call rather than
handed over. Each of the three cites the new test.

### The character ceiling, measured on the rendered form

Round 26's own fixture (`tests/test_round26._thread_mailbox`, ~110-word messages, `Re:` on every
reply), through the shipped `call`. "Cap off" is this same build with `host_chars=None` — i.e. the
token ceilings alone, which is the pre-round-26 enforcement:

| messages | cap off | served | × cap | what the served response is |
|---|---|---|---|---|
| 5 | 15,859 | **16,657** | 0.67 | 5 rows at `body_clean`, `truncated_by: null` |
| 7 | 21,063 | **21,863** | 0.87 | 7 rows at `body_clean`, `truncated_by: null` |
| 12 | 31,179 | **22,781** | 0.91 | 12 rows at `body_clean`+`snippet`+`stub`, `truncated_by: mailweave`, `partial: true` |
| 30 | 51,771 | **17,320** | 0.69 | 5 rows + one declared run of 25, `truncated_by: mailweave` |
| 60 | 16,822¹ | **17,620** | 0.70 | 5 rows + one declared run of 55, `truncated_by: mailweave` |

¹ at 60 the *token* ceiling was already binding with the cap off, so that figure is not the
pre-round-26 size; it is this build's own with one ceiling removed.

The two round-25 reviewers' own probes, re-run unmodified:

* `/tmp/rmcp25/p6_hostcap.py` — every size from 3 to 40 now under the cap (max 23,467 at n=8, 0.94×),
  `truncated_by: 'mailweave'` and `partial: true` from n=8 up. Was 27,957 at n=7 and 70,682 at n=40.
* `/tmp/rdisc25/r15_mcp_wire.py` — 3 → 9,456; 12 → 23,990 (was 25,358, over); 20 → 13,912
  (was 34,638); 40 → 14,132 (was 57,838); 60 → 14,352 (was 59,700).
* Round 24's twelve-thread bulk search (`search teleportation`): 23,705 characters, one source,
  17 withheld records, 11 `not_included_sources`, `truncated_by: mailweave`. It was 39,106 with the
  cap off.

The line, stated once: **on ordinary ~110-word messages this build serves seven at full body depth
and degrades from eight up.** R-MCP's fixture crosses at 8, R-DISC's at 12, mine at 8. That is the
honest range the three fixtures support, and it is the range R-MCP predicted.

### What each test establishes

| test | what it establishes |
|---|---|
| `test_no_served_response_crosses_the_hosts_character_cap[5,7,12,30,60]` | the rendered `CallToolResult`, measured in the host's unit, at the five published sizes |
| `test_a_thread_that_would_cross_the_cap_comes_back_declared_rather_than_cut` | `truncated_by: mailweave`, `partial: true`, and every one of the thirty messages still a row, a declared run member or a withheld record — with an affordance on each |
| `test_the_record_of_a_host_cap_reduction_names_the_host_cap` | the `why` on the records the reduction produced names the 25,000-character cap, not "the declared token ceiling" — a reader sent to `max_disclosed_tokens` would be sent to the wrong argument |
| `test_a_response_that_cannot_be_brought_inside_the_cap_declines_in_band` | the other lawful outcome is a `budget_exhausted` **result** with a `retry_with`, never an exception |
| `test_the_character_estimate_bounds_the_rendered_result[10 shapes × 3 tools]` | every served response is inside the cap over a matrix that varies message count, body length, distinct-sender count and recipient-list length — the dimensions R-DISC-036 said round 25's matrix held constant. It holds the estimate's bound by its *consequence*; the inequality itself is the table below |
| `test_the_surface_refuses_an_over_cap_result_even_when_the_ladder_passed_it` | the surface's own measurement, exercised on an envelope built with the ladder's cap off, so it is not a check the ladder makes unreachable |
| `test_the_participant_index_is_charged_what_the_wire_carries` | the charge with a hand-written oracle, and that it varies with sender count rather than being a constant |
| `test_the_estimate_charges_the_participant_index_the_wire_actually_carries` | the narrowing is one rule, so what the ladder charged is what the envelope emits |
| `test_a_layout_nobody_serves_carries_no_character_cap` | the cap is opt-in for measurement and mandatory for serving, with both halves asserted |

### What I could not establish

1. **The token estimate is still under the rendered wire on one shape.** On round 24's twelve-thread
   bulk search the estimate is 2,351 and `wire_tokens` is **2,724** — 14 % under. The gap is the text
   mirror's per-affordance line and the mirror line of each withheld record, neither of which the
   60-token record charge covers. I did not raise `WITHHELD_RECORD_TOKENS`, because at 80 a
   previously-fitting hundred-record response stops fitting the 9,000-token ceiling and an unrelated
   lexical-ladder fixture becomes a decline — a collateral capability loss for a finding outside the
   eight. It matters only when the applied ceiling is close to the estimate, i.e. when a caller
   lowers `budget.max_disclosed_tokens`. **R-DISC-032 is fixed for the field it names and the general
   property is not yet universally true.** Filed below.
2. **The character estimate is conservative, and conservative costs answers.** Measured shape by
   shape while the constants were derived, `layout_chars` against `rendered_chars`: worst slack
   **+530 characters**, ratios **1.03 to 1.68** over seventeen shapes across all three tools
   (loosest on collapsed-run-heavy responses; tightest on the twelve-thread bulk search at 1.043
   and a thirty-message thread at 1.033). Never negative — which is the direction that matters —
   and the cost of that is real. R-DISC's 400-message, 110-word fixture
   now *declines*: the estimate says 26,821 characters against 25,000, and the rendered form would
   have been about 23,000. Tightening it far enough to serve that response would put the estimate
   under the rendered form on the shapes where it currently has 3 % of margin, which is the defect.
   Filed below with the number.
3. **`_meta["anthropic/maxResultSizeChars"]` is still discarded at `on_call_tool`.** R-MCP called
   reading it "the principled version and not required for the demo", and PF-6 owns it. The constant
   is enforced; the channel is not read.
4. **The 9,000 and 12,000 token figures are untouched**, as both reviewers scoped. Re-deriving them
   from the measured cap is PF-6's.

---

## Part 3 — the fence and the filename (R-MCP-016)

### What changed

* `envelope/wire._sender_chosen_scalar` + the `SenderScalar` annotation: one line, printable, and
  bounded. Applied to all four fields of `AttachmentMetadata` — the one model on this wire whose
  values a sender chooses, and the one model the rule in `envelope/reasons.py` had never been
  applied to.
* `constants`: `MAX_ATTACHMENT_FILENAME_CHARS` 255, `MAX_MIME_TYPE_CHARS` 255, `MAX_PART_ID_CHARS`
  64, `MAX_ATTACHMENT_ID_CHARS` 4096 — refusal bounds, never truncations, for `MAX_ADDRESS_CHARS`'
  stated reason.
* `surface/rendering._every_line_is_one_record` + `MirrorLineBreak`: the **structural** half. Every
  line the mirror composes is checked to be one line, with exactly one exemption — the fenced
  content block, keyed on `CONTENT_LINE_PREFIX`, a prefix this module writes and no interpolated
  value can claim. `surface/server.call` turns the refusal into a declared internal failure that
  echoes no mail text.

`/tmp/rmcp25/p3_filename.py`, unmodified: the control (`invoice.pdf`) is unchanged — `isError=False`,
one fenced block, **0 disagreements, 0 forged lines**. The attack no longer produces a served
response at all; the response model refuses it and the call comes back as a declared failure.
Before: `disagreements=7`, four attacker-chosen lines in the residue, a real message body
re-attributed to `FORGED-9`.

### The sweep: every wire field a sender can influence, and the bound on each

Enumerated by walking every `SealedModel` in `envelope/wire.py` and classifying each `str`-bearing
field by who chooses the value.

| field | who chooses it | bound |
|---|---|---|
| `AttachmentMetadata.filename` | sender (`Content-Disposition`) | one line, printable, ≤ 255 — **added this round** |
| `AttachmentMetadata.mime_type` | sender (`Content-Type`) | one line, printable, non-empty, ≤ 255 — **added** |
| `AttachmentMetadata.part_id` | Gmail, from the sender's MIME tree | one line, printable, ≤ 64 — **added** |
| `AttachmentMetadata.attachment_id` | Gmail, from the sender's MIME tree | one line, printable, ≤ 4096 — **added** |
| `Content.text` | sender (body, snippet) | fenced with the per-response nonce; refused outright where it contains the nonce (`envelope.fence`) |
| `ThreadParticipant.address` | sender (`From`/`To`/`Cc`/`Reply-To`) | `is_an_address`: addr-spec shape, one line, no whitespace, ≤ 320 |
| `ThreadParticipant.{authored,coauthored,addressed,reply_to,mentioned}` | Gmail ids | `Source` refuses a citation of a message the source does not disclose |
| `MailboxProvenance.labels[]` | Gmail label ids | one line, non-blank (`is_one_line`) |
| `ReplyParentAmbiguous.message_id_header` | sender (`Message-ID`) | `ReasonScalar` (one line, non-empty) **and** `structural.is_probeable`: length-bounded, `MSG_ID_RE`, no `"{}()` |
| every other `Reason` parameter | MailWeave, or the caller's query | `ReasonScalar`; `GmailNumericId` where the shape is known |
| `MessageRow.id`, `.reply_parent_id`, `Source.thread_id`, `WithheldRecord.{id,thread_id}`, `CollapsedRun.member_ids`, `ErrorEntry.message_ids`, `Source.withheld_here`, `ThreadStructureReport.*` | Gmail (opaque ids) | not sender-chosen; covered structurally by the renderer invariant |
| `ScanScopeEntry.q`, `ParsedQuerySummary.{operators,terms,timezone}`, `EmptyDiagnosis.*` | the **caller** | `MAX_QUERY_CHARS`; caller text, not mail text |
| `*.why`, `*.note`, `*.scope`, `Score.*`, `Shortlist.rule`, `PoolBlock.*`, `Source.source`, `Counters.quota_units_label` | MailWeave | strings this server wrote |

Two things the sweep establishes that a per-field audit would not: **the subject never reaches the
wire at all** (there is no subject field on any wire model), and **there is no `display_name`** —
what survives is `distinct_display_names`, an integer.

### What each test establishes

| test | what it establishes |
|---|---|
| `test_the_sanitiser_that_was_supposed_to_stop_this_does_not_stop_it` | executed rather than argued: `strip_invisible_characters` removes Cf and passes `\n` and `\r` through, which is why the bound belongs on the model |
| `test_no_sender_chosen_attachment_field_can_carry_a_line_break[4 fields]` | each field refuses `\n`, `\r`, U+2028 and `\x1b`, and an ordinary attachment still constructs |
| `test_an_over_long_sender_chosen_value_is_refused_rather_than_truncated` | the bound is a refusal, not a silent rewrite |
| `test_the_text_mirror_refuses_to_write_a_value_that_spans_two_lines` | the structural half, on a field that is *not* the one the attack came through |
| `test_the_sender_chosen_fields_are_the_ones_the_sweep_names` | the table above, executed: address, label, `Message-ID` and the fence, each refusing at its own boundary |
| `test_every_line_a_real_response_mirrors_is_one_record` | the positive control — a guard that refused everything would pass the two above and ship nothing |

### What I could not establish

**The refusal costs the call.** A message whose attachment filename carries a control character now
makes `mailweave_get_attachment` fail as a declared internal error rather than come back as a fact
about the message. The graceful form — strip the control characters and declare a `Reduction`, which
is exactly what `content/mime.py` already does for category Cf — needs a new `HiddenConstruct` member,
and that enum is rendered onto the wire, so it is a schema change with a version bump. Out of scope
here; filed below.

---

## Part 4 — the most likely failure on demo day (R-MCP-017)

### What changed

`surface/server.call` gains `except (ConsentFailed, TokenStoreError) as credential:` →
`declined(ErrorCode.AUTH_REAUTH_REQUIRED, message=str(credential))`. `str()` already carries
GMAIL-06's instruction in GMAIL-06's own words.

`/tmp/rmcp25/p4_token.py`, unmodified, through the real SDK client:

```
C. a refresh that FAILS mid-session, on a live tool call
   isError=True  code=auth_reauth_required
   "...run `mailweave auth login` to re-authorise the read-only client (auth_reauth_required)."
D. the credential store becomes unreadable mid-session
   isError=True  code=auth_reauth_required
   "no credentials at ...; run `mailweave auth` to authorise the read-only client"
```

Both were `-32603 Internal server error` with empty `data`.

### The half of R-MCP-017 I did **not** take, and why — this is the "have I trusted a peer?" answer

R-MCP called clause 2 the principled repair and preferred it: wrap `self._token.access_token()`
inside `GmailClient._request` so `gmail/faults.py`'s "no bare exception crosses this layer" becomes
true, and a `GmailAuthExpired` lands on the clause `call` already has.

**I implemented it, and the suite showed it undoes R-MCP-006 — the previous round's own repair.**
`surface/runtime.start` distinguishes four startup credential causes *by exception type*, and
re-typing `ConsentFailed` as `GmailAuthExpired` collapses "a refused refresh" and "a narrowed grant"
into one answer:
`tests/test_round25.py::test_each_startup_credential_failure_reports_itself_as_itself` went red on
two of its four parameters. That is precisely the over-broad reporting round 25 narrowed, arriving
again through a door R-MCP did not check. I reverted the wrap, left a paragraph at the call site
saying why the obvious repair is not there, and added
`test_the_startup_path_still_tells_the_four_credential_causes_apart` so the next person who reads
R-MCP-017 and reaches for clause 2 gets a red test rather than a quiet regression.

### What each test establishes

`test_a_credential_failure_reaches_the_client_as_the_instruction_it_is` — **eight cases**: two
producers (a refused refresh, a vanished credential store) × all four tools, each driven through the
shipped `call`, asserting `isError: true`, `code == auth_reauth_required`, and `mailweave auth` in
the remediation. All four tools, because a partition that held for one of four would be the same
finding waiting on a different call.

### What I could not establish

The failure is injected at `open_client`, which is where a vanished store raises. A refresh refused
*mid-request* is covered by `/tmp/rmcp25/p4_token.py` scenario C (a real `StoredTokenProvider` on an
injected clock against a token endpoint answering `400 invalid_grant`) rather than by a test in this
repository, because reproducing it in-suite needs the round-25 startup harness and I judged the
executed reviewer probe sufficient evidence for a path the suite already covers at startup.

---

## "Have I trusted a peer?"

Three times, and each time it cost something:

1. **R-MCP-017's preferred repair.** Executed, it undid R-MCP-006. Section above.
2. **R-DISC's account of the end-to-end 0-of-10.** R-DISC attributed `r04_hit_ranks.py`'s "protected
   top-10 == the 10 earliest, five times out of five" to `hit_ranks`. I fixed `hit_ranks`, re-ran
   `r04`, and it still reports 0 of 10 — because on that fixture the depth map is decided by
   `_fetch_bodies`' `sorted(evidence_ids)[:10]`, not by disclosure at all. Had I taken the number as
   the fix's acceptance criterion I would have chased a defect the fix cannot reach, or worse,
   "fixed" something until the number moved.
3. **R-DISC-033's proposed mechanism.** "Re-run the ladder at a lowered ceiling" is what I built
   first. It does not work: the token ceiling is too blunt a proxy — at the ceiling where the
   ladder would fully split a twelve-source response, the response no longer fits that ceiling at
   all, so the descent skips the only layout that fits the character cap. The fix had to be a
   two-unit fit predicate inside the ladder.

And one place I did **not** trust myself: every character constant in `envelope/measure.py` is the
measured residual of the rendered form over a shape matrix, and the matrix is in the suite
(`test_the_character_estimate_bounds_the_rendered_result`), not in my scratch directory.

---

## New, filed and left

| # | what | where | why not here |
|---|---|---|---|
| **N-1** | **The bodies a search fetches are the ten lowest ids.** `_fetch_bodies(run, sorted(run.evidence_ids), cap=MAX_BODY_FETCHES_L1)`; `plan.depth_for` can only give `body_clean` where a body exists, so on a thread where every message is a hit, *which messages get depth* is oldest-K by construction, for every query — and no disclosure-layer rule can reach it. This is what R-DISC-031(b)'s end-to-end probe was measuring. Severity: **HIGH** — it is EV-02's degenerate strategy one layer below where A11 was applied. | `server/src/mailweave/retrieval/ladder.py:1438`, `:1520`, `:1553` | outside the eight; it is a retrieval fetch-budget policy, and the fix (score the shortlist before spending `max_body_fetches` on it) is a rung change |
| **N-2** | **The token estimate is 14 % under the wire on a withheld-record-dominated response** (bulk twelve-thread search: 2,351 vs 2,724). Uncharged: the text mirror's per-affordance line, and the mirror line of each withheld record beyond the 60-token constant. | `server/src/mailweave/envelope/measure.py` | raising the record charge to 80 turns a previously-fitting hundred-record response into a decline; the collateral is bigger than the finding |
| **N-3** | **The character estimate's slack costs answers within ~10 % of the cap.** R-DISC's 400×110-word fixture: estimate 26,821, cap 25,000, rendered form would be ≈23,000 → declines with a narrower retry where it would have fitted. | `server/src/mailweave/envelope/measure.py` constants | tightening far enough puts the estimate *under* the rendered form on the shapes that currently have 3 % margin, which is the defect this round fixed |
| **N-4** | **A control character in a sender-chosen filename costs the `get_attachment` call**, reported as an internal defect rather than as a fact about the message. The graceful form is a declared `Reduction`, which needs a new `HiddenConstruct` member — a wire-vocabulary addition. | `server/src/mailweave/envelope/wire.py`, `content/mime.py` | schema change with a version bump; the safety property is met as scoped |
| **N-5** | **`map_id` is 409 characters per source** — with `structure`, the largest per-source item in the host's unit; a twelve-source response spends ~4,900 characters on signed handles. A caller that never redeems one pays for twelve. | `server/src/mailweave/handles/mint.py` | a real trade (handles are the whole of WS-06) and a question for the owner, not an implementer |
| **N-6** | **`grep maxResultSizeChars server/src` still returns nothing**, which R-MCP used as the test for "is there a character measure". The measure exists under `HOST_RESULT_CHAR_CAP` / `rendered_chars`; a reviewer repeating the grep verbatim will get the old answer. | naming only | noted so the next review greps for the right name |
| **N-7** | **A twelve-source search is close to the cap by scaffolding alone.** Round 24's bulk mailbox serves at 23,705 characters with **one** source and eleven declared as not-included: eleven threads' worth of `map_id`, stamps and structural blocks do not fit beside their own rows. The published `max_hit_threads = 12` and the host's cap are in tension, and the cap wins. | `constants.MAX_HIT_THREADS` vs `HOST_RESULT_CHAR_CAP` | a published-cap question for PF-6 and the owner |

---

## Gates

Run on the working tree after every change above.

```
ruff check .                    All checks passed!
ruff format --check .           199 files already formatted
mypy --strict server/src        Success: no issues found in 84 source files
python -m tools.guards          guards clean: forbidden-import, generative-client, gmail-endpoint,
                                ground-truth-isolation, scope-literal, unaudited-disk-write,
                                unwrapped-http-client over server/src
pytest -q -m "not network"      2,737 passed  (2,691 before; 46 added)
python -m tools.rubric_status   PASS 6 · FAIL 0 · BLOCKER 0 · NOT TESTED 107
```

Reintroduction: eight new entries in `tests/fixtures/replants.py` (**R115–R122**), one per behaviour
this round changed. `test_every_replant_anchor_matches_exactly_once_in_the_tree` and
`test_every_behaviour_these_rounds_changed_fails_a_test_when_it_is_removed` both pass, so every
anchor matches exactly once and every `caught_by` citation catches its own plant individually.
R98's anchor was re-written where round 26 changed the line it names.

No rubric criterion was marked PASS. ROUTE-01 was not restored. `FINDINGS_LEDGER.md` and
`RUBRIC_TRANSITIONS.md` are untouched. `docs/ARCHITECTURE_AMENDMENTS.md` gains **A12.3**, a *record*
of the second ceiling for A12's own reason: a change to a published surface belongs there rather
than only in a round report.
