# ROUND 25 — implementer's report

**Round:** 25, a fix round on WS-11 (disclosure) and WS-15 (MCP surface), before the live
milestone. **Work order:** `docs/reviews/ROUND_25/WORK_ORDER.md`, Parts 1–6.
**Gating reviewers:** R-DISC (Parts 1, 3, 4) and R-MCP (Parts 2, 5, 6).

I ran every reproduction the work order names before changing anything, and I saw each defect
myself. What follows is what changed, what each test establishes, and — kept deliberately
level with the rest — what I could **not** establish.

**This round was written in two sittings.** The first did Parts 1–5 and Part 6's named items and
stopped mid-round. The second opened with an **audit** — every reviewer reproduction re-run
against the finished tree, on the rule that *a file having been changed is not evidence that a
finding was fixed* — and it found two findings still live in files this round had edited. Both are
now fixed, both are marked as second-sitting work below, and the audit's own result is the first
section of this report. Where this report says "verified", a probe was executed and its output is
quoted; where it says "not established", nothing was executed that establishes it.

**Nothing was marked.** `FINDINGS_LEDGER.md` and `RUBRIC_TRANSITIONS.md` are untouched, no
rubric criterion moved, `ROUTE-01` was not restored, retry/backoff was not touched, and I read
no reviewer probe set as an oracle: I ran `/tmp/rdisc23/` and `/tmp/rmcp24/` to *see the
defects*, and every assertion in my diff is written against a fixture and an oracle of my own.

---

## What I reproduced before touching anything

| Repro | What I saw |
|---|---|
| `/tmp/rdisc23/p02_disc01_pairs.py` | `queries: 6 pairs: 15 pairs whose included set DIFFERS: 0`; every row `(TERM_OVERLAP,) score=4` for all six |
| `/tmp/rdisc23/p16_ordering_collapse.py` | `the top 18 of the query-aware ranking is exactly the +/-2 window? True` |
| `/tmp/rmcp24/p5_fence.py` | a forged `withheld` line and a forged `next call` line at column zero, outside the fence; `disagreements()` returned 2 |
| `/tmp/rdisc23/p08_step1_inflates.py` | `step 1 e4_query_scored_fill 9300 -> 12370`, then `DisclosureLadderExhausted` |
| `/tmp/rdisc23/p19_measure_equality.py` | `measure_tokens 8300`, `ceiling 9000`, rendered **526,006 + 176,909 chars** |
| `/tmp/rdisc23/p04b_floor_hole.py` | `floor members the planner computed: []` on a 60-message all-hit chain; `t-m015 is disclosed; its direct child t-m016 is withheld` |
| `/tmp/rdisc23/p06_shipped_band.py` | `per=700 *** DisclosureLadderExhausted escapes assemble()` |
| `/tmp/rmcp24/p3_faults.py` | 404/500/429/403 → `ESCAPES GmailRequestRejected / GmailUnavailable / GmailRateLimited / GmailAuthExpired` |
| `/tmp/rmcp24/p14_expiry.py` | `total token exchanges: 1 (1 = never refreshed)` |
| `/tmp/rmcp24/p13_startup.py` | four planted credential failures, three of them reported as `auth_profile_underivable` |

### And what I re-ran at the end, against the finished tree

The round was written in two sittings and the second began with an **audit**, because a file
having been changed is not evidence that a finding was fixed. Every reproduction above, plus
`p01`, `p04`, `p07`, `p09`, `p10`, `p11`, `p12`, `p13_reductions_record`, `p14_wire`,
`p15_wire_ratio`, `p18_cross`, `p19_follow`, `p21_seg`, `p22_minrepro`, `p23_force`, `p24_sampling`
and `p25_conc`, was executed against the finished tree — the R-DISC probes in a fresh scratch copy
with `mailweave`, `mailweave_harness` and `tests` asserted resolving inside it and `docs/` present.

**Two findings whose files this round edited turned out not to be fixed by those edits**, and
reading the diff would have marked both done:

* **R-DISC-026** — `disclosure/plan.py` and `disclosure/ladder.py` were both edited this round,
  and every `Band.EVIDENCE` row still carried `fill_score = 0`. `p12_scoring_claims.py`:
  `protected top-5 == the 5 EARLIEST hits by position? True`, in both arms. **Fixed in the second
  sitting** — §"Which hit keeps its body" below;
* **R-MCP-010** — `surface/rendering.py` was edited this round, and the row mirror still carried
  four fields, so `reason` was rendered and never read back and `mailbox` was not rendered at all.
  **Fixed in the second sitting** — §"The text mirror" below.

Everything else in Parts 1–5 reproduced as **fixed**. Four findings from Part 6's tail remain open
and are named in §"Still open, and why".

**Two corrections to the state I was told I was inheriting.** The handover said the suite had one
failing test (`test_every_behaviour_these_rounds_changed_fails_a_test_when_it_is_removed`) and
that this report did not exist. Neither was so: the manifest ran 111 CAUGHT / 0 MISSED before
anything was touched — checked three ways, alone under pytest, through `run_replants` directly,
and in a full `-m "not network"` run under the default random ordering — and this file was already
here. I did not edit the manifest on the strength of a failure I could not reproduce; the entries
added since are for the two new fixes and nothing else.

**And one thing I found while reproducing, which no review filed.** `assemble` read the
**pre-ladder** plan (`disclosure.threads`) for its rows and the **post-ladder** layout
(`disclosure.layout`) for its collapsed runs. So every A.9a step was computed, declared in
`truncated_by`, and then discarded before the wire: a thread that reached step 5 emitted its
collapsed members as rows *as well*, and `Source` refused the response. It is reachable today
on the shipped path — a 240-message thread does it — and it means the round-23 ladder never
reached a client at all. Fixed in Part 3; planted as **R100**.

---

## Part 1 — the thesis (A11, R-DISC-017/018)

### What changed

**`disclosure/weights.py`.** A11's rule is about a component's *behaviour on the thread*, so
it is computed from the thread and never written against the subject:

* `CANDIDATE_FACTS` names every fact the five predicates read (`subject`, `observed_text`,
  `addresses`, `inside_query_date_window`, `seconds_from_nearest_hit`,
  `positions_from_nearest_hit`), and `fact_values` reports one candidate's value for each;
* `message_discriminating_facts(candidates)` is the facts whose value differs between at
  least two candidates of the thread. A fact with one value across the candidate set is a
  **thread-level fact**;
* `components_of` gained a `facts` parameter. The **published score is unchanged** — it is
  always computed over all of `CANDIDATE_FACTS` and is what a row's reason names. The same
  predicates are asked a second question: what would you say if you could see only the facts
  that differ within this thread? That answer is `FillScore.anchored`;
* `rank` then removes any component whose surviving fire covers **every** candidate or none,
  because a component that admits everything separates nothing;
* the ordering key is `(-anchored_value, position)`. `POSITION_ADJACENCY` and `DECISION_CUE`
  are not in it.

**`disclosure/plan.py`.** `_score_of` returns `FillScore.anchored_value`, so the A.9a ladder's
degradation order and step 3's protection are decided by the same quantity `rank` is. Using
the published sum there would have put `POSITION_ADJACENCY` back in charge of which filled
rows lose their depth first — the same defect one layer down.

`E4_WEIGHTS` is byte-identical to what round 23 published. A11 is not a new number and not a
new weight, and `test_the_published_weights_did_not_move_when_the_admission_rule_changed`
executes that sentence.

### DISC-01, on my own ≥5-query single-thread set

`tests/test_disclosure_round23.py::shared_subject_thread` is the thread **Gmail actually
sends**: 24 messages, **one** subject line — `quarterly borogrove slithy toves outgrabe mimsy
plan` — on every one of them, so all five query terms are thread-level facts. What separates
the messages is each one's own snippet, which carries a different subset of the five (the bits
of its index: a mechanical construction, not a hand-tuned one).

```
queries: 6   pairs: 15   pairs whose included set DIFFERS: 15

  borogrove          |included| = 12   m001 m003 m005 m007 m009 m011 m013 m015 m017 m019 m021 m023
  slithy             |included| = 12   m002 m003 m006 m007 m010 m011 m014 m015 m018 m019 m022 m023
  toves              |included| = 12   m004 m005 m006 m007 m012 m013 m014 m015 m020 m021 m022 m023
  outgrabe           |included| =  7   m009 m010 m011 m012 m013 m014 m015
  mimsy              |included| =  7   m017 m018 m019 m020 m021 m022 m023
  borogrove+slithy   |included| = 18   m001 m002 m003 m005 m006 m007 m009 m010 m011 m013 m014
                                       m015 m017 m018 m019 m021 m022 m023
```

**15 of 15**, against round 23's **0 of 15** on the same shape. The sets are non-empty, so
"they differ" is not "nothing was ever disclosed" — asserted, because an empty fill would pass
a differ-test the lazy way.
(`test_five_queries_over_one_thread_produce_different_included_sets`.)

Every admitted row carries a reason naming at least one component **anchored in what the
caller wrote**, and the anchored set is a subset of what fired
(`test_every_included_row_carries_a_reason_that_names_a_query_derived_mechanism`).

### Proof the E4 ranking is not the ±2 window on a shared-subject thread

Baseline F(±2) on that thread selects **10** positions:
`m001 m002 m006 m007 m009 m010 m014 m015 m017 m018`.

```
  borogrove          ranked 12   top-10 == window?  False
  slithy             ranked 12   top-10 == window?  False
  toves              ranked 12   top-10 == window?  False
  outgrabe           ranked  7   top-10 == window?  False
  mimsy              ranked  7   top-10 == window?  False
  borogrove+slithy   ranked 18   top-10 == window?  False
  subject-only thread ranked  0  ==     window?     False
```

Two rows of that table are load-bearing and they fail differently, which is why both are
asserted (`test_the_e4_ranking_on_a_shared_subject_thread_is_not_the_plus_minus_two_window`):

* **the subject-only thread** — every candidate fires `TERM_OVERLAP` from the shared subject
  and from nothing else. The fixture asserts that first (`fired == every candidate`), so it is
  the case A11's sentence is about. The ranking is **empty**: a component that fired
  identically on every candidate ranks and does not admit, and an empty ranking is not the
  window;
* **the two-term query** — 18 of the 23 candidates are admitted, so the admitted set is
  strictly *larger* than the window and the question is which 10 come first. Under round 23's
  key the first 10 are the window exactly. I checked that directly: with the ordering key
  reverted to the published sum, `top-10 == window? True`. That is replant **R95**, and it is
  the assertion that isolates the ordering half from the admission half.

`toves+outgrabe+mimsy` admits **0**, and that is A11 working rather than a bug: 21 of the 23
candidates carry one of the three in their own snippet, the two that do not are hits and hits
are not candidates — so the component fires on every candidate again and admits none of them.

### Explainable for a query nobody has written

The rule is computed over the **fact**, not over the field, and
`test_the_admission_rule_is_computed_from_the_thread_not_written_against_the_subject` runs it
over a different fact: a query naming an address that is on every message admits nothing, and
the same component admits the moment that address stops being thread-constant. A rule that
special-cased the subject would pass for the subject and fail there.

### What I could not establish

* **that the E4 order is *better* than the baseline's.** It is a mechanical sum of five
  predicates with no measured relation to relevance. WS-16 owns that and I did not run it.
* **that `POSITION_ADJACENCY` and `DECISION_CUE` still earn their published weights.** After
  A11 they contribute to the score a row *reports* and they order nothing — A11 forbids
  exactly that ordering role. I said so in `rank`'s own docstring rather than quietly keeping
  them in the key. Whether a weight whose only remaining effect is descriptive should still be
  published is WS-17's sweep and the owner's, not mine.
* **that A11 had reached everywhere it needed to.** It had not, and the audit caught it: the
  rule reached the *fill* and left the *evidence* band scored zero, so A.9a step 3 still
  protected the oldest k hits by position. That is R-DISC-026 and it is fixed below; I record
  it here because the honest reading is that Part 1's first pass was half of A11, not all of it.
* **the `[UNSET]` pair-difference threshold.** 15/15 passes any threshold, but the number is
  unregistered and I did not invent one.

---

## Part 2 — the fence (R-MCP-002)

### What changed

`surface/rendering.py::split_fenced` closes on **the nonce**. The nonce is read off the
block's **own opening marker** (`^<<<(mw-[0-9a-f]+) `) rather than taken on trust, and two
properties make that sound: `envelope.fence.fence` refuses to fence text containing the nonce,
so the content between the markers provably cannot spell the closer; and `fence` writes the
opener at the *start* of the block, so the first marker on a content line is the real one
however many well-formed-looking markers the body goes on to contain. An optional `nonce`
argument gives a caller holding the response's own `fence_nonce` the stronger check.

Two secondary hardenings, both in the safe direction: a content line whose block does not open
with a marker is **not** a fence and is left in the residue whole (an unopened block may not
swallow the lines beneath it); and a block whose closer never arrives is handed back as one
block rather than spread into the residue. And `disagreements()` now runs
`fence_disagreements()` first, which reads `fence_nonce` **out of the structured mapping the
client also receives** and refuses any block not opened *and* closed by it.

### The fence, attacked my own way

Re-run in the second sitting against the finished tree, as ten whole responses through the shipped
service and the shipped renderer — each body being the attack line followed by four forged lines
(a `withheld` record, a second source with `stated_total: 400` and a `map_id`, a message row, and
a `next call`). `leaked` counts forged lines that reached `split_fenced`'s **residue**, which is
the half every reader below runs on:

```
literal >>> at end of first line     withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
closer with trailing spaces          withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
closer preceded by a tab             withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
a nonce-shaped closer, not ours      withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
full-width confusables (＞＞＞)        withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
guillemets (»»»)                     withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
a whole valid-looking fenced block   withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
closer alone on its own line         withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
three closers in one body            withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
HTML-escaped closer (&gt;&gt;&gt;)   withheld=0 sources=1 blocks=1 leaked=0 disagreements=0
```

`sources=1`: the fabricated second source is not read as a source. `withheld=0`: the fabricated
withheld record is not read as one. And the eleventh attack, the one a sender cannot mount but the
code has to survive — a body containing **this response's own nonce** — is refused at fencing with
a named message, and reaches the caller as an internal failure that says *"retrying mints a new
nonce"* rather than a traceback.

The table below is the same set as the parameterised test asserts it.

Every body below **contains** the closer, in each of the forms a sender can write it, followed
by four lines shaped like the ones this connector writes about itself: a `withheld` record, a
second `source thread` with its own `stated_total`, a `message ... at position ... role`
row, and a `next call`. Round 24's test planted a body containing **no** `>>>` at all.

| Attack | Escaped the fence? |
|---|---|
| the literal closing sequence `>>>` | no |
| the closer with trailing spaces | no |
| the closer after a tab | no |
| a nonce-shaped closer that is not this nonce (` mw-deadbeefdeadbeef>>>`) | no |
| the closer with no leading space (`x>>>`) | no |
| unicode confusables (`＞＞＞`) | no |
| guillemets (`»»»`) | no |
| a whole well-formed fenced block under a different nonce | no |
| a body containing **this response's own nonce** | refused at fencing, not escaped |
| a forged `content (...)` line with no opening marker | swallows nothing |
| a block whose closer never arrives | stays one block; no line of it reaches the residue |

`test_no_closing_sequence_a_sender_can_write_ends_the_fence` asserts, for each: the block is
the whole body byte for byte; no residue line begins with a forged shape; and
`disagreements()` is empty. `test_a_real_response_whose_body_contains_the_closer_keeps_its_two_forms_in_agreement`
runs the same attack **end to end** through the shipped service and renderer.

### What I could not establish

The fence is per-response and unguessable, and **WS-14 owns the rest of the injection
posture** (trust labelling everywhere, connector-voiced fields, identity splitting). This
round makes the closing side unforgeable and nothing more. A body containing the nonce is
still refused with a `FenceViolation`, which now reaches the caller as a named internal
failure rather than a bare `-32603`; re-minting the nonce and retrying inside the server would
be a better answer and I did not build it.

---

## Part 3 — the estimate is the wire (A11's second rule; R-DISC-019, 022; R-MCP-003)

### What changed, in one place

`envelope/measure.py` holds the rule and `disclosure/layout.py` **calls it** rather than
re-implementing it:

* `row_tokens(text)` = `ROW_STRUCTURAL_TOKENS` + `WIRE_COPIES_OF_DISCLOSED_TEXT` × the text's
  whitespace tokens. `text is None` is a stub row and **still costs its structure**. That is
  A11's second rule, and it is why no rung can enlarge the response any more;
* `collapsed_run_tokens(members)` charges a run its own structure plus a per-member cost — the
  ids serialise twice, once as `member_ids` and once inside the expansion affordance
  `surface/expansion.py` mints;
* `WITHHELD_RECORD_TOKENS` charges each `withheld` record, off the **same quantity** on both
  sides (`accounted_ids - present_ids` on the layout, `envelope.withheld` on the envelope).
  Without it A.9a steps 7 and 8 looked free, and a response that could not carry 400 rows
  "fitted" 400 pointers to them and rendered more wire than it started with;
* `RESPONSE_STRUCTURAL_TOKENS` is what every response costs whatever it holds;
* `layout_tokens` adds the same constant and the same per-record charge, so
  `layout.cost() == measure_tokens(envelope)` **survives** — R-DISC verified that property on
  five shapes and it is asserted here on the shipped path as well as at the planner.

`WIRE_COPIES_OF_DISCLOSED_TEXT = 2` is not a fudge: the disclosed text is serialised in
`structuredContent` **and** in the text mirror MCP-03 requires beside it. Counting it once was
half of why the estimate sat 20× from the wire.

`disclosure/plan.py::full_dump_tokens` is charged through the same `row_tokens`, because a
dump is a response too and DISC-04's ratio was otherwise comparing two different units.

**Three more repairs in the same pass**, all of them consequences of the measure becoming the
wire rather than additions to it:

* `_collapsible` reads the **depth**, not the band (R-DISC-030). A FILL row step 1 degraded to
  a stub, and a FLOOR row with no observed text, are stub rows in a hit-bearing thread and
  A.9a step 5 is written about stub rows;
* `_degrade_through_head_truncation` gained a final `snippet -> stub` rung — **recorded as a
  deviation in amendment A12.2**, because A.9a stops at snippet and R-DISC-023 said the
  missing rung was owner-visible. It is reached last (the driver stops the moment the layout
  fits), a stub row is still a member, and with `_collapsible` fixed it is collapsible into a
  declared run. It converts a 400-message all-matching thread from *200 pointers or an
  exception* into a complete map: 5 rows, 1 declared run of 395 members, nothing withheld;
* step 6 now checks the counterfactual A.9a's own "if and only if" names —
  `cheapest_membership_cost`, the response with every message reduced to a bare stub row —
  which only became *reachable* once the rung above existed. `ceiling.why` carries the figure,
  so the field states a fact the payload can be checked against instead of a sentence selected
  by two numbers differing (R-DISC-023).

The driver gained its **third** gate, `assert_cost_did_not_rise`, applied to every step but
step 6 — so it covers a rung nobody has written yet, which is the whole reason the other two
gates live in the driver.

`assemble` now reads the **ladder's output**, which is the defect I found while reproducing.

### The wire-versus-estimate relationship, stated once and measured on the rendered form

> **The estimate the ceiling is enforced against is an upper bound on the rendered response,
> in the same whitespace-token unit** — where "the rendered response" means the two things a
> client is handed: `structuredContent` serialised, plus the text mirror beside it.

Measured on the shipped path, `_answer(...)` → `render(...)`, six thread sizes:

```
  msgs  estimate  wire_tok  wire/est  ceiling  json_chars  text_chars  total_chars
     5      1180       825      0.70     9000        6450        1849         8299
    20      3220      2460      0.76     9000       18717        5966        24683
    60      8660      6820      0.79     9000       51437       16926        68363
   120      1645      1200      0.73     9000       10173        1998        12171
   240      2005      1560      0.78     9000       13773        1998        15771
   400      2485      2040      0.82     9000       18573        1998        20571
   700      3385      2940      0.87     9000       27573        1998        29571
```

(Re-measured **after** the text mirror gained `reply_parent`, `mailbox` and `map_id` — see
§"The text mirror". Every row of a response got longer, so this table had to be taken again;
the ratio moved from 0.68–0.86 to 0.70–0.87 and the bound still holds. Had I not re-measured I
would have shipped a structural constant derived against a shorter row.)

Against round 23's measured ratios of **20 to 85**, in the wrong direction. The bound is
asserted, not described: `test_the_estimate_is_an_upper_bound_on_the_rendered_wire`
parametrised over six sizes, and `_measure` in `tests/test_mcp_surface_round24.py` — which
re-implemented the production estimate while its docstring said it measured the wire
(R-MCP-003) — is now `wire_tokens(structured, text_of(structured))`, so the round-24 shape
matrix's ceiling assertion is a wire measurement too. R-MCP-003's own worst case, following
the server's collapsed-run affordance on a 300-message thread, is inside its declared ceiling
measured that way (`test_following_a_collapsed_runs_affordance_returns_its_members`).

### What I could not establish — and this is the important half

**That 9,000 estimated tokens is below the target client's [VERIFIED] 25,000-*character* cap.
It is not.** The table above runs at 6.9 to 8.6 characters per estimated token, so a response
at the full ceiling could render ~62,000–77,000 characters. This round moves the *quantity*
the ceiling is compared against; the *figure* is `[DESIGN, set by PF-6]` and re-deriving it in
the host's own unit is PF-6's, exactly as R-DISC recommended. **DISC-06 must not be marked
while that stands**, and I am not asking for it to be.

Two smaller ones: `FLAT_MAP_MESSAGE_BOUNDARY` fell from 225 to 75 because it is derived from
the per-row charge, and DISC-04's efficiency numbers are in new units — the round-23 report's
`0.216 / 0.881` should not be quoted, as R-DISC already said.

---

## Part 4 — the floor, with a hand-written oracle (R-DISC-021)

### What changed

`floor_of` records a member that is **itself a hit**. Round 23 skipped it — "it is already
present at evidence depth, and a second record for it would be a second disposition" — and the
first half of that sentence is true while the conclusion is not: `floor_of`'s output is *two*
things at once, the members whose depth the promotion rule decides and the set A.9a may never
remove. Skipping a hit removed it from the second as well. A.7a is satisfied by the
**banding** (`plan_thread` tests `hit_ids` first, so a hit gets exactly one row in
`Band.EVIDENCE`), not by the omission. `dependence` is `None` for such a member: promotion is
a statement about depth and a hit is already at evidence depth.

`floor_pairs_of` returns **every** `(evidence, member)` obligation, not one per member —
`floor_of` records a member reachable from two hits against the first, which is right for the
*reason* a row carries and wrong for the *guarantee*. `Layout.floor_pairs` carries them, and
`assert_floor_intact` reads them so it can tell the one lawful removal (a member leaving
together with every hit that needs it, in a declared whole-source split) from every other. That
reading is **recorded as amendment A12.3** because it is a change to how OD-3's "membership is
absolute" is read, and that is the owner's sentence, not mine.

### Stopping the floor being checked against its own derivation

`ORACLE_FLOOR` in `tests/test_round25.py` is **typed out by hand** for a named 12-message
chain with hits at 3, 4 and 9, with the derivation written in the comment above it:

```
hit 3: parent 2, child 4    hit 4: parent 3, child 5    hit 9: parent 8, child 10
=> {2, 3, 4, 5, 8, 10}
```

3 and 4 are in it **because they are each other's parent and child**, which is exactly what
round 23 dropped. `test_the_floor_is_what_the_reply_tree_says_it_is` compares `floor_of`'s
output against that tuple, and asserts A.7a separately (one row per message, hits banded
EVIDENCE). `test_every_disclosed_hit_keeps_its_reply_parent_and_children_at_every_step` derives
the obligations from `parent_of`/`children_of` — the observation's own reply tree — and checks
the payload against them at six ceilings from 30,000 down to 900.
`test_a_hit_that_is_another_hits_floor_member_is_never_withheld` runs R-DISC's own reproduction
shape (a chain every message of which matched) as an assertion, and
`test_the_ceiling_never_converts_a_floor_member_into_a_withheld_record` drives A.9a step 8
directly at three ceilings chosen so that 16, 10 and 4 evidence messages remain disclosed —
because a payload with no evidence left in it has no obligations to break, and a defective step
8 would pass through that state on its way to passing a lazier test.

**No test in my diff compares a derivation with itself.** The floor oracle is hand-written; the
obligations come from the reply tree, not from `floor_of`; `_measure` measures the wire; the
segment boundary is asserted against the literals `9,000` and `120` rather than against the
expression it is computed from.

Re-checked over the second sitting's additions rather than inherited. The hit-ranking oracle is
typed out (the hits `toves` reaches are named by position, not read off `hit_ranks`). The mirror
tests compare `read_back(text_of(s))` against `extract(s)` — a renderer plus a parser against a
direct read of the mapping, which is the round-trip and not a self-comparison — and each fact is
*perturbed* first, so a mirror reading a constant fails. The one place two derivations of the same
quantity are compared is `test_the_two_arms_sacrifice_evidence_depth_in_the_same_order`, and what
that test is and is not worth is stated where it is introduced rather than left to be assumed.

### What I could not establish

* **`FloorDependence.CONSTRAINT_CARRIER` still has no producer** (R-DISC-024). R-DISC suggested
  hit-members as the natural carrier once they are recorded; the finding's own required fix
  says to record them with `dependence=None`, and I followed the finding. So clause 3 remains a
  wire vocabulary member reachable only from a hand-built matrix. It needs an owner's call
  between giving it a producer and removing it, and I did not make that call.
* **promotion still buys nothing** (R-DISC-025). `FLOOR_BASE_DEPTH` is snippet, thread maps are
  `format=metadata`, so a promoted member reaches the same depth an unpromoted one does.
  Unchanged and unfixed.
* **the promotion rule's clause 1 is still `relation is PARENT` in disguise** (R-DISC-024) and
  the A.8a lexicon still misses most reversals. R-DISC-027's tokenizer fix moves the
  sentence-final case; the lexicon's coverage is PF-13's.

---

## Part 5 — the surface can tell "declined" from "broke" (R-MCP-001, 006, 007, 009)

### What changed

* **`surface/server.py::call`** catches `GmailFault` and branches on `ERROR_SURFACE[fault.code]`
  — the table `gmail/faults.py` puts the code on the exception class *for*. It also catches
  `DisclosureLadderExhausted` (a declared refusal with `budget_exhausted` and an executable
  retry, never an exception out of the tool handler — R-DISC-020), and `ValidationError` /
  `FenceViolation` as **internal** failures rather than `INVALID_PARAMS`, because MailWeave's
  own model refusing MailWeave's own output is not the caller's request being malformed
  (R-MCP-005). The caught `ValidationError` is chained and never rendered — Pydantic's report
  quotes what it refused, and here that is a response built out of mail.
* **`partition.declined`** gained `unanswerable`, the one door out of the in-band side, and it
  says so in the message: D.11's table records where a code travels *when there is a response
  for it to travel on*, and a rate limit that aborted the whole call has none.
* **`auth/consent.StoredTokenProvider`** has the expiry check and the single-flight guard its
  own docstring had been promising WS-15. `TOKEN_REFRESH_SKEW_S` is derived (one retry ladder
  plus a round trip, so a token that passes the check cannot expire *during* the call it was
  fetched for), the deadline is against `time.monotonic` (injected, so a test can cross an hour
  without waiting one), a grant that states no `expires_in` is **not given an invented
  lifetime**, and `invalidate()` exists for a caller that saw a 401.
* **`surface/runtime.start`** re-raises `GmailAuthExpired`, `ConsentFailed` and
  `TokenStoreError` as themselves and translates only what
  `auth_profile_underivable` actually means.
* **`auth/tokenstore._check_mode`** checks existence before permissions, so `serve` refuses
  with a cause and a next step instead of a `FileNotFoundError` traceback.

### The partition test, driven through real producers

`test_every_gmail_fault_lands_on_the_side_its_own_code_puts_it_on` plants an HTTP status behind
the **real** `GmailClient` and calls a tool. Round 24's test called `declined(code, ...)`
directly for all eighteen codes: it tested the renderer against the table and never that any
real condition reached the renderer.

| Producer | Before | After |
|---|---|---|
| 404 on `threads.get` (a deleted message) | `-32603 Internal server error` | `isError: true`, `partial_source_failure` |
| 500 on `threads.get` (an outage) | `-32603` | `upstream_unavailable` |
| 429 on `messages.get` (a rate limit) | `-32603` | `upstream_rate_limited`, "no partial answer to carry it" |
| 403 on `messages.get` (a revoked grant) | `-32603` | `auth_reauth_required`, **with `mailweave auth login` in the remediation** |

Four startup failures, four distinct messages
(`test_each_startup_credential_failure_reports_itself_as_itself`), and the positive control
that narrowing the catch did not narrow the success path:

```
refresh refused (invalid_grant)  ConsentFailed        ... run `mailweave auth login` ...
granted scope narrowed           GrantedScopeMismatch ... granted a different scope set ...
getProfile 500                   AuthProfileUnderivable  auth_profile_underivable
getProfile 401 (revoked)         GmailAuthExpired        auth_reauth_required + `mailweave auth login`
```

`test_the_access_token_is_refreshed_when_it_expires` crosses the hour on an injected clock:
one exchange, no second exchange inside the lifetime, exactly one more past it.
`test_the_refresh_is_single_flight` drives four **real threads** through a barrier and asserts
one exchange and one token — a guard that is held rather than a guard that is present.

### What I could not establish

* **that a 401 mid-call triggers a re-exchange.** The provider refreshes on **expiry**;
  refreshing on a 401 needs the Gmail client to call back into the provider, which is inside
  the retry ladder, and the work order forbids touching retry/backoff. `invalidate()` is there
  for whoever does it. R-MCP-009's mechanism (reproduced by planting a 401) therefore still
  ends in a refusal rather than a recovery — but it is now `auth_reauth_required` with the
  instruction on it, not an opaque protocol error, which was the half R-MCP said to do first.
* **wall-clock behaviour on a real grant.** REACHABLE-IF-TIME, and no test in this build runs
  an hour.
* **anything needing a live account** — OD-6 criteria 2, 3 and 4-on-real-mail.

---

## Part 6 — SETUP as a stranger reads it, and the rest

* **`docs/SETUP.md` §2** gains step 5 and the command: `chmod 600
  mailweave-server-oauth.json`, with the reason (a browser download arrives 0644 and both
  `auth login` and `serve` refuse it). §7's troubleshooting table gains a row for the
  *mode* refusal naming all three files `doctor` checks, a row for `credentials.json does not
  exist` pointing at step 4, and a row for a narrowed grant; and the
  `auth_profile_underivable` row now says explicitly that a *credential* problem reports
  itself as one of the three rows above and never as that code.
* **`cli.doctor`** takes `--client` and checks the OAuth client file's mode, printing
  `chmod 600 <path>`. `test_doctor_diagnoses_the_oauth_client_files_mode` asserts both
  directions — exit 1 with the mode named at 0644, exit 0 with `oauth client file: ok` at 0600
  — and `test_setup_tells_a_stranger_to_chmod_the_client_file` reads the document.
* **`DisclosureLadderExhausted`** is a declared refusal (above), and it is now much harder to
  reach: `/tmp/rdisc23/p06`'s 700-message case is served as a complete collapsed map. The
  exception's "what is left" sentence is **counted off the layout** instead of asserted —
  round 23's said "the remaining payload is floor membership" whatever the remainder was.
* **R-DISC-027** — `content_tokens` strips trailing `.`/`-` from a token that does not need
  them, so `decided.` and `decided` are one token. Addresses, dates, decimals and hyphenated
  words are untouched (asserted).
* **R-DISC-030** — `_collapsible` reads the depth (Part 3).
* **R-MCP-004** — `budget.max_disclosed_tokens` works. `Ceiling` accepts a declared departure
  in **either** direction (amendment A12.4); `normal` stays the published figure and `why`
  names the caller's request. A minimum is published and enforced
  (`MINIMUM_DISCLOSED_TOKEN_REQUEST`, derived as one response plus one row), because below it
  no response can be built at all.
* **R-MCP-011** — `view: null` is refused; `part_id: ""` is refused.
* **R-MCP-013** — `query` carries `maxLength` in the schema **and** in the parser, and
  `httpx.InvalidURL` is typed as `GmailRequestRejected` at the Gmail layer's single call site
  (raised immediately, not fed to the backoff state: no request was made and rebuilding the
  same URL would fail the same way).
* **R-MCP-015** — amendment **A12** records round 24's D.1 additions, and round 25's own three
  deviations, as things awaiting the owner's ratification.
* **R-MCP-005** — closed, though as a *consequence* rather than directly. `_collapsible` reading
  the depth means the collapse step takes the residue instead of stopping at stub capacity, so
  every previously-unanswerable shape answers. `p22_minrepro.py`, re-run: threads of 226/250/300/500
  messages with 224–300 named ids at `view: "stub"`, all seven **OK**, each a complete map
  (`rows=0 runs=1 included == stated_total`). Worth naming that R-DISC-019's structural charge
  *lowered* the boundary this finding named from 225 to 75, so had it not been fixed it would have
  become more reachable, not less. Its second half — MailWeave's own `ValidationError` reported to
  the caller as `INVALID_PARAMS` — is fixed in `call` (above).
* **R-MCP-014's six false sentences** — five are now true of the code (the fence's nonce, the
  `_measure` docstring, the partition test's reach claim, `runtime`'s re-auth sentence,
  `StoredTokenProvider`'s promise), and a sixth of the same shape was found and fixed during the
  audit: `plan._candidates`' docstring said it returned "every message that is neither a hit nor a
  floor member" and its own `continue` excludes hits only. One remains, and it lives in
  `docs/reviews/ROUND_24/IMPLEMENTER.md`, which is a closed round report and not mine to edit —
  amendment A12.4 records the correction instead.

---

## Which hit keeps its body: R-DISC-026, found open by the audit and fixed

This is the finding the audit found untouched, and it matters more than its MEDIUM severity
suggests, because **it is Part 1's defect one band over**.

**What was true.** `DISCLOSURE_TOP_K_HITS`'s own docstring says the protected hits are "decided by
the published E4 score, ties by thread position. Deliberately not by recency and not by arrival
order". They were not. The fill is the only producer of a score and the fill never scores hits, so
every `Band.EVIDENCE` row carried `fill_score = 0`; `_top_k_hit_ids` sorts by `(-fill_score,
position)`, so **the tie-break was the whole selection** and the protected set was
`sorted(hits, key=position)[:5]` — for every query, in both arms. `_degrade_band` reads the same
field, so evidence lost depth newest-first for the same reason. EV-02's degenerate-strategy guard
names a fixed newest-K or oldest-K policy by construction; this was one, wearing the published
score's name. R-DISC measured it: `distinct evidence fill_scores=[0]`, `protected top-5 == the 5
earliest hits by position? True`.

**What changed.** `disclosure/plan.py::hit_ranks(thread, query)` scores the hits with the same five
predicates and the same published weights, ranked **among themselves**, under A11's
discriminating-facts rule computed over the hit pool — so the shared subject, a participant on
every message, and both proximity facts (which are zero for a hit by definition) cannot decide
which hit keeps its body. `plan_thread` writes it onto the evidence rows' `fill_score`. No weight
moved; this is A11 applied where round 25 had applied it to the fill and not to the evidence.

It is computed **outside the `Selector`**, deliberately: DISC-02 compares the two arms at equal
budget and they must differ in which rows the *fill* buys, not in which evidence bodies the ladder
sacrifices. An arm that kept different evidence would be running a different ladder.

**Measured**, on `shared_subject_thread(messages=32, hit_every=4)` — 8 hits, one subject carrying
all five terms, each message's snippet carrying the terms its index selects — query `toves`:

```
hits whose own text carries the term : m004 m012 m020 m028   (anchored score 4)
the other four                       : m000 m008 m016 m024   (anchored score 0)
protected top-5   = [m000 m004 m012 m020 m028]
the 5 earliest    = [m000 m004 m008 m012 m016]
protected == oldest-K?  False        (it was True, for every query, in both arms)
```

and where the query separates no hit from another, every value is 0 and thread position decides —
the old behaviour, kept, now as the **stated fallback** rather than as the whole rule. That case is
asserted too, so the fix cannot be read as "the ordering became arbitrary".

Two tests and manifest entry **R112**. `test_which_hit_keeps_its_body_is_not_the_oldest_k_by_position`
carries the oracle, typed out (positions 4, 12, 20, 28 are the hits `toves` reaches, because bit 2
of the index selects it). `test_the_two_arms_sacrifice_evidence_depth_in_the_same_order` asserts
both arms produce identical evidence scores and identical protected sets — and **that second test
is worth less than the first, so here is what it is worth**: because `hit_ranks` is
selector-independent by construction, the equality is close to structural. Its force is as a
regression guard on *where the code lives*; it fails the day someone moves hit scoring into a
`Selector`, which is the change that would silently break DISC-02's comparison. It is not
independent evidence that the score is right.

---

## The text mirror: R-MCP-010, found open by the audit and fixed

**What was true.** `MIRRORS` round-tripped thirteen facts and the row entry carried four —
id, position, role, depth. `reason` and `linkage` were **rendered and never read back**, so a
rendering that wrote `reason semantic cosine 0.99` on every row — naming a mechanism this system
does not have — passed 2,615 tests. `mailbox` was not rendered at all, so a client reading the
mirror could not tell a Spam or Trash result from an inbox one; that is OD-6 **criterion 4**'s own
word. `map_id` was not rendered, so a text-only client could not follow a handle at all.

**What changed**, in `surface/rendering.py`:

```
source thread <id>: included <n> of stated_total <n>, as_stub <n>, map_id <id|none>
  message <id> at position <n>: role <r>, depth <d>, linkage <l>,
      reply_parent <id|none>, mailbox <spam|trash|spam+trash|default|unobserved>, reason <…>
```

`reason` stays **last** because it is the only free-text field on the line and the only one whose
value can contain a comma: every field a reader parses sits in front of it and the reader takes the
rest of the line. `mailbox_token` has **three** states, not two — a row whose labels no observation
stated says `unobserved` rather than reporting a negative, which is `MailboxProvenance`'s own rule
and not a second one — and `outside_the_default_mailbox` is not spelled separately, because it is
`bool(regions)` in the model and a second spelling could only ever disagree with the first.

`_extract_rows`/`_read_rows` carry eight fields now, and a new `map_ids` mirror carries the handle.
Round 24's own sensitivity test refused the new mirror until it had a perturbation, which is that
guard working as designed.

**No amendment entry, and here is why.** AD D3 publishes *"`structuredContent` mirrored to text"*
and MCP-03's acceptance names "totals, roles, **reasons** and affordances"; it does not publish a
line format. This change makes more of the structured form reach the text and none of it reach it
differently, so it moves toward the published requirement rather than away from it — the opposite
shape from A12.1's additions to a published *signature*. If the owner disagrees, the change is one
function and a table, and it is named here.

Two tests and manifest entries **R113** and **R114**.
`test_a_fabricated_row_fact_fails_the_mirror_rather_than_passing_the_suite` plants each of the four
facts in the structured mapping and asserts the mirror moves with it — with
`extract(planted) != extract(payload)` asserted *first*, so a mirror reading a constant fails
rather than passing vacuously. `test_a_spam_row_says_so_in_the_text_a_model_reads` has the three
token strings written out by hand and checks the rendered line.

**What I did not do.** R-MCP-010 also names `participants`, `asked_for`, `scan_scope`,
`empty_diagnosis`, `counters` and the freshness stamps. I rendered the four the finding calls the
minimum — `mailbox`, `reply_parent_id`, `reason`, `map_id` — plus `linkage`, and left the rest. The
reviewer's stronger ask, *"assert `MIRRORS` covers every fact any tool description claims"*, is
**not done**: it needs the tool descriptions' claims enumerated as data, which is a `Claim`-shaped
change I did not want to make in an audit pass.

---

## Still open, and why

Four findings from Part 6's tail are **not fixed**. Each reproduces exactly as filed against this
tree — I ran each rather than assuming — and each is left deliberately.

| Finding | Sev | Verified still true | Why not here |
|---|---|---|---|
| **R-DISC-024** — the promotion rule's three clauses | MEDIUM | `p09_promotion.py`: a one-word parent **and a parent with no observed text at all** are both promoted, so clause 1 is `relation is PARENT` in disguise. `p10_constraint_carrier.py`: clause 3 fires on no input this system produces | Clause 1 needs A7's span provenance carried into `MemberFacts`; clause 3 needs `admitted_by` per decomposition probe, or the vocabulary member removed. Both are design changes in a rule OD-3 names. R-DISC's own suggestion — hit-members as the natural carrier — conflicts with the finding's other instruction to record them with `dependence=None`, which is the one I followed |
| **R-DISC-025** — promotion decides a label, not a depth | MEDIUM | `p11_promotion_depth.py`: promoted and unpromoted floor members carry the same depth; `FloorPromoted` is the only difference in the payload | The reviewer's two options are "build the budgeted fetch" or "state in OD-3's terms that depth is not currently earned". The first is WS-10's accountant and T-CD3 forbids disclosure initiating it; the second is an **owner's** sentence |
| **R-DISC-028** — silent depth demotions | MEDIUM | `p13_reductions_record.py`: `body_clean → snippet` drops ~1,150 tokens with **no reduction record and no size count**; the eight `LadderStep` records never reach the wire | A `depth_reduced` reduction kind plus a response-level step block changes the wire vocabulary and the field census — an A12-shaped surface change that should belong to the round that owns it. **DISC-03's "silent reductions: 0" is not currently true, and this is why** |
| **R-MCP-012** — `segment` is inert | LOW | `p21_seg.py`: twelve calls at 230/300/500/900 messages with `segment` absent, `0` and `1` — all twelve return the identical whole map; no affordance mints one | Implementing it is WS-16's; removing it is another D.1 narrowing needing an amendment entry. A published argument that does nothing is a claim wider than the code, and it still is one |

---

## Have I trusted a peer?

**Yes, in four places, and here they are.**

1. **`_step_8_would_fit` asks step 8 a hypothetical by running it against a ceiling of zero.**
   That is one implementation asked twice rather than two implementations — deliberately — but
   it means step 7's decision inherits every bug step 8 has. If step 8 ever stops being
   monotone in what it takes, step 7 will split sources it should not.
   `test_step_7_does_not_split_a_source_that_step_8_could_have_saved` carries a positive
   control (step 8 really could have fitted it) so at least the two cannot both be wrong
   silently.
2. **`layout_tokens` charges withheld records off `accounted_ids - present_ids` and
   `measure_tokens` off `envelope.withheld`.** I asserted the two agree on the shipped path
   over four thread sizes and on the planner's own path over three shapes. I did **not** prove
   they must agree for every response `assemble` can build — a cap that files a withheld
   record for an id the layout never held would break it, and the failure mode is the envelope
   refusing a response the ladder thought had fitted. That is the safe direction, and it is
   still a peer trusted.
3. **`ROW_STRUCTURAL_TOKENS = 120`, `WITHHELD_RECORD_TOKENS = 60`,
   `COLLAPSED_RUN_MEMBER_TOKENS = 3`, `RESPONSE_STRUCTURAL_TOKENS = 500`** are derived by
   measuring the rendered form and pinned by a test that measures the rendered form — over
   **my** fixtures. A row with many reductions, many attachments and a long reason costs more
   wire than any row I measured. The bound is asserted, not proved.
4. **The relative floor gate falls back to the absolute rule when `floor_pairs` is empty**, so
   a `Layout` built without the reply tree (WS-15's expansion path builds one directly) is
   never silently ungated. I did not construct the case where that fallback is the only thing
   defending a floor; I made it fail closed instead.

And one thing I did **not** trust: round 23's fixtures. Three of its behavioural claims invert
on `shared_subject_thread`, which is the shape Gmail produces, and I moved the tests onto it
rather than keeping the shape that made them pass.

### Three more, from the second sitting's audit

5. **I did not trust this round's own first sitting, and that was the right call.** The audit's
   whole method was to run the reviewers' reproductions rather than read the diff, and it found
   **two findings whose files this round had edited and whose defects were still live**
   (R-DISC-026, R-MCP-010). Both would have been marked fixed by anyone reading the changed-file
   list. `p12_scoring_claims.py` and a `grep` of `MIRRORS` took about a minute each.
6. **I did not trust the handover's claim of a failing test either — and the failure mode there
   is the opposite one, which is worth naming.** Had I assumed the report was right, the obvious
   move was to edit the manifest until something changed, which would have damaged a manifest
   that was correct. The first thing I ran was the manifest, alone; then through `run_replants`
   directly; then in a full randomised suite run. 111 CAUGHT, 0 MISSED, before anything was
   touched.
7. **`hit_ranks` trusts `message_discriminating_facts`** rather than re-deriving A11's rule for
   the hit pool. That is deliberate — one rule, one implementation, stated once — but it is a
   dependency: if A11's rule is wrong it is now wrong in two places for one reason, and the only
   test that would catch it going wrong *for hits* is
   `test_which_hit_keeps_its_body_is_not_the_oldest_k_by_position`.

**The peer a reviewer should attack first.** `WIRE_COPIES_OF_DISCLOSED_TEXT = 2` and
`ROW_STRUCTURAL_TOKENS = 120` bound the wire *as this renderer writes it today*. That is a measured
property of a rendering, not a theorem, and the margin at 700 messages is 13 %. Adding three fields
per row to the text mirror this round ate part of it (0.86 → 0.87). A future rendering that adds
two more eats the rest. The test would catch it — it is parameterised across the shape matrix and
runs on the shipped path — and that is the only reason the constant is defensible.

---

## The honest OD-6 table

| # | Criterion | What this round touches | What remains |
|---|---|---|---|
| **1** | The server starts through a documented command and **refuses without a valid credential, with a named reason** | All three defects that made this false: SETUP's missing `chmod 600` and the troubleshooting rows (R-MCP-008); `serve`'s `FileNotFoundError` traceback (R-MCP-007); four credential failures under one code with the wrong remedy (R-MCP-006). `doctor` now diagnoses the file the refusals name | The document has not been walked from a clean `HOME` **by a stranger** since I changed it. I ran the commands; I am not a stranger to them |
| **2** | Connection to an authorised Gmail account | Nothing. The token provider now survives past one access-token lifetime, which is a precondition rather than the criterion | Everything. Needs a live account and a consent screen; OD-4 forbids me one |
| **3** | Claude invokes it and retrieves a real email or thread | The three things that made a *large* thread unanswerable: the ladder inflating the response and then refusing it (R-DISC-019), `DisclosureLadderExhausted` escaping as an unhandled exception (R-DISC-020), and ≥225 named ids at stub depth being unanswerable and blamed on the caller (R-MCP-005). A 700-message all-matching thread is now a complete map, re-verified. Every Gmail failure arrives as a named refusal rather than `-32603` (R-MCP-001), and following the server's own collapsed-run affordance returns 2,240 wire tokens against a declared 9,000 instead of 272 % over it (R-MCP-003) | The criterion itself: a real client, a real account, real mail. And a response at the full ceiling still renders more characters than the host accepts — PF-6's number, not this round's |
| **4** | Stable handles, truthful scope, **Spam/Trash provenance** | Handles: unchanged, and still redeemed across a real process boundary (re-verified, `p18_cross.py`). Truthful scope: unchanged. **Provenance moved**: the row's `mailbox` is now in the text mirror as well as the structured form, and round-tripped, so a client reading the form a model reads can tell a Spam result from an inbox one (R-MCP-010). `map_id` and `reply_parent_id` likewise, and a fabricated `reason` on a row now fails a test instead of passing 2,615 | Spam/Trash provenance **on real mail with real Gmail labels**. Every label in these tests is a fixture's string, and OD-6 says a mock is not evidence for this. The mirror's remaining omissions (`participants`, `asked_for`, `scan_scope`, `empty_diagnosis`, `counters`, the freshness stamps) are named above and not done |
| **5** | Reproducible smoke test and a **written demonstration procedure** | The written procedure works when followed (Part 6), and it no longer stops working after one access-token lifetime (R-MCP-009) | The procedure has not been executed against a live account. The smoke test is offline and deterministic, as before |
| **6** | Review | This report, and the reviewers' | R-DISC and R-MCP re-reviewing what I changed. I have not marked anything and I am not asking for the milestone |

**I do not recommend declaring OD-6's milestone**, and I do not think this round earns it. The
honest summary is that round 25 removed reasons the milestone would have failed *if it had been
attempted*; it did not advance the milestone, because the milestone's remaining half is a live
account and this round could not touch one.

What I claim is narrower and exact. The two findings that defined the round are closed and
executed: six materially different queries over one thread produce **15 of 15** differing fills
for a reason a stranger can read, and no mail text I could write — ten shapes, including unicode
confusables and a whole valid-looking fenced block — closes the fence. Three degenerate strategies
that had shipped under the published policy's name are gone (admission on a thread-level fact,
ordering by `POSITION_ADJACENCY`, and evidence protection by oldest-K). No degradation step can
make a response larger, the declared ceiling bounds the rendered wire in tokens and is measured on
the rendered form, and the floor is checked against a hand-written oracle rather than against its
own output. And a fabricated `reason` on a row now fails a test instead of passing the suite.

What remains is in the tables above, in plain sight: four open findings, the character cap PF-6
must re-derive, and everything that needs a live account.

---

## Gates

Re-run after every change, on this tree:

| Gate | Result |
|---|---|
| `ruff check server/src tests tools harness` | All checks passed |
| `ruff format --check .` | 198 files already formatted |
| `mypy --strict` | Success: no issues found in **171** source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,691 passed**, 0 failed (2,615 at the start of the round) |
| `pytest -q tests/test_replants.py` | 4 passed — **114** manifest entries, every anchor matching once, every file changed, every `caught_by` citation catching **individually**: **114 CAUGHT, 0 MISSED** |
| `python -m tools.rubric_status` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — unchanged |

**Replant manifest: 114 entries.** Twenty-one are round 25's (R94–R114). R112 (a hit scored zero,
so oldest-K keeps its body) and R113/R114 (the row mirror stops reading back what it renders; a
spam row says nothing about its mailbox) were added in the second sitting for the two fixes the
audit made — one entry per **behaviour**, which is why R112 is separate from R95 rather than
folded into it: they are A11's ordering rule in two different bands, and either can be reverted
without the other.

Four round-23/24 entries were **re-anchored rather than deleted** because this round's fixes moved
the code they plant into — R71 (step 7's floor filter now protects a property the relative gate
made expressible, so the citation names that property), R72 (round 23 had to widen step 8's
candidate set because `floor_of` excluded hits, which was itself the finding; dropping the floor
clause is now the reintroduction), R73 (`PlannedRow.cost` calls `row_tokens`), and R81
(`declined`'s partition clause gained `unanswerable`, and the old anchor had slipped one line down
onto a clause that decides only the wording — a plant into it changed nothing and reported CAUGHT
for a defect it had not introduced). **No entry was deleted**, so none needs a stated reason for
no longer applying.

The three properties every CAUGHT row rests on, all executed on every run rather than asserted:
the scratch tree is the **whole** tree including `docs/` (`tools/rubric_status.py` reads
`docs/RELEASE_RUBRIC.md`, and a copy that omitted it failed a tree nothing had been planted into);
`mailweave`, `mailweave_harness` **and** `tests` are each asserted to resolve **inside** the
scratch copy and **not** into the working tree; and every test the manifest cites is run on the
pristine copy first, so a CAUGHT row is a test that changed its mind rather than one that was
already red.

---

## What a reviewer should attack first

1. **A11's rule on a query nobody has written.** Build a thread whose discriminating fact is one
   I did not think about — a date window covering part of a thread, a participant added halfway
   down a recipient list — and check that admission tracks it. The rule is computed over the fact
   and names no field, which makes it *explainable*; explainable is not correct.
2. **`ROW_STRUCTURAL_TOKENS = 120` against the character cap.** The estimate bounds the wire in
   tokens, measured, and does **not** bound it in characters: a 60-message reply is 68,363
   characters against a 25,000-character host cap. Part 3 says so; the figure to move is PF-6's.
3. **The four findings in §"Still open, and why"**, each of which reproduces exactly as filed.
4. **`hit_ranks` on a thread whose hits differ in a fact other than their text.** I built the term
   case. The participant and date-window cases run through the same code and I built no fixture
   for them.
