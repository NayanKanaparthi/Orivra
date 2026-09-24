# ROUND 25 — R-DISC review (the ordering was fixed; the admission rule meets `Re:`, and the estimate is still not the wire)

**Reviewer:** R-DISC, independent instance, 2026-09-06. Gating reviewer for round 25 Parts 1, 3
and 4; the disclosure domain, which owns DISC-01..06, PART-05 and EV-03. Verified by execution
per `AGENT_LOOP.md` §4/§5/§5a, classified for **reachability** and for **OD-7 urgency**
separately.

**Source, tests, `FINDINGS_LEDGER.md`, `RUBRIC_TRANSITIONS.md` and `RELEASE_RUBRIC.md`
untouched.** `diff -rq` between the working tree and my pre-review snapshot at `/tmp/rd25`
reports no difference; this file is the only thing I wrote inside `/root/mailweave`.

My probes are `/tmp/rdisc25/r*.py` (the `q*.py` and `_env.py` already in that directory when I
arrived were not written by me, and I read none of them as an oracle; my own environment module
is `renv.py` and my own fixtures are `rlib.py`). My vocabulary is invented (`borogrove`,
`slithy`, `toves`, `outgrabe`, `mimsy`, `brillig`); my senders are `.example` / `.invalid`
(RFC 2606/6761). **No fixture below contains real or realistic personal mail text.**

---

## Environment

| Gate | Result (re-run by me, before and after all probing) |
|---|---|
| `ruff check server/src tests tools harness` | All checks passed |
| `ruff format --check .` | 198 files already formatted |
| `mypy --strict` | Success: no issues found in **171** source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **EXIT=0**. The `-q` summary line does not flush in this environment, so independently counted two ways: `--co -q` per-file sum = **2,691**, and the progress stream carries **2,691** `.` marks with **no** `F`/`E`/`s` |
| `pytest -q tests/test_replants.py -rA` | 4 passed. Manifest read directly: **114** entries |
| `python -m tools.rubric_status` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — unchanged |

Every gate figure in `ROUND_25/IMPLEMENTER.md` reproduces exactly. I did not treat that as
evidence of anything beyond the gates.

### Scratch trees and isolation

Two full copies, both including `docs/`:

* `/tmp/rd25` — my read-only review tree. `renv.py` asserts `mailweave.__file__`,
  `mailweave_harness.__file__` **and** `tests.__file__` all resolve inside it, and that
  `docs/RELEASE_RUBRIC.md` and `docs/ARCHITECTURE_AMENDMENTS.md` are present.
* `/tmp/rdisc25/plant_floor` — the Part 4 plant tree, same three assertions, printed before the
  plant ran.

I also **refreshed `/tmp/rdisc23/tree` to today's code and re-ran every one of the round-23
probes** (`p01`–`p24`) against the round-25 tree, as instructed. Results are folded in below;
`p04c.py` fails to import (`ModuleNotFoundError: tests`) because it sets `sys.path` differently
from its siblings — that is a defect in the predecessor's probe, not in the tree, and I did not
repair it.

---

## Reachability and urgency, as I applied them

* **Reachability (§5a).** REACHABLE = reproducible today by driving `LadderRunner` →
  `assemble` (and, where stated, `surface.server.call`) against a synthetic mailbox behind
  `httpx.MockTransport` with the **real** `GmailClient` and the **shipped defaults** — no
  ceiling override, no monkeypatch of the policy. REACHABLE-AT-PLANNER = reproducible by
  calling `mailweave.disclosure.disclose` directly. I use no other class; nothing below is
  unreachable.
* **Urgency (OD-7), separate from severity.** *Fix before the demo* = the defect **prevents
  safe and truthful end-to-end use**: it puts a false statement about the response in front of
  a model, or it loses evidence with no withheld record, or it makes the live demonstration or
  the OD-7 point-4 comparison measure something other than what it claims to measure.
  Everything else is *track*. I have applied this strictly in both directions: three findings
  below are HIGH and still *track*, and one is MEDIUM-flavoured in severity and still
  *fix before the demo*, because OD-7's line is about safety and truth, not about size.

---

## Priority 1 — is A11 implemented as stated, or narrower?

### The rule generalises. It is not written against the subject.

`r01_a11_generality.py`. A11's own defect paragraph names three ways the same degeneracy
arrives, so all three are the rule's claim rather than my extension. Twenty-message thread,
hits at 0/6/12/18:

```
A. TERM_OVERLAP via the SUBJECT
  subject carries 'brillig', no message's own text does -> fill = 0
  term in every 3rd message's OWN text                  -> fill = 3

B. PARTICIPANT_MATCH via the address fact
  amy on EVERY message, query names amy                 -> fill = 0
  amy on every 4th message, query names amy             -> fill = 3   {004, 008, 016}

C. TEMPORAL_PROXIMITY via the query's own date window
  whole thread inside the query window                  -> fill = 0
  first half of the thread inside the window            -> fill = 5   {002,003,004,008,009}
```

Thread-constant ⇒ admits nothing; varying ⇒ admits exactly the messages that vary (the ids
missing from B and C are hits and E2 floor members, which are banded before FILL). The rule is
computed over `CANDIDATE_FACTS` and names no field. **An attachment on every message is a
non-question**: `CANDIDATE_FACTS` is
`{addresses, inside_query_date_window, observed_text, positions_from_nearest_hit,
seconds_from_nearest_hit, subject}`, `ThreadInput` carries no attachment fact, and no predicate
reads one — so an attachment could not admit anything with or without A11.

**This half of A11 is real and I could not break it.** It is the principled route
R-DISC-017 offered as (b), and it was implemented as (b).

### But the rule is defeated by the two characters Gmail puts in front of every reply

`r06_re_prefix.py`, `r08_root_message.py`. `weights.fact_values`'s own docstring says:

> "two messages whose subjects differ only in a `Re:` prefix carry the same subject *as the
> components read it*, and A11's question is whether the component can tell them apart."

Executed:

```
content_tokens('quarterly borogrove slithy toves outgrabe mimsy plan')      -> 7 tokens
content_tokens('Re: quarterly borogrove slithy toves outgrabe mimsy plan')  -> 8 tokens
equal? False   symmetric difference: ['re']
```

`content_tokens` keeps `re` as a content token. Gmail sends `Subject: S` on a thread's **root**
and `Re: S` on every reply — round 23's own R-DISC report says exactly this about
`assemble._thread_input`, and I confirmed it on the shipped path (`r05_why_zero.py`: the root's
subject tokenises to 7, every reply's to 8). So whenever the pool A11's rule is computed over
contains the root **and** at least one reply, `message_discriminating_facts` classifies
`subject` as **message-discriminating**, and A11 stops holding back the archetypal thread-level
fact.

Two pools exist and the root lands in exactly one of them. `r08_root_message.py`, over the
implementer's own `shared_subject_thread(messages=24)`, query `toves`, at every hit placement:

```
  hits at         |fill| flat   |fill| Re:   hit_ranks flat   hit_ranks Re:
  (0, 8, 16)               10           10              [0]             [4]
  (1, 9, 17)               12            0              [0]             [0]
  (2, 10, 18)              12            0              [0]             [0]
  (3, 11, 19)               9            0              [0]             [0]
  (4, 12, 20)               6            0              [4]             [4]
  (0, 4, 8, 12, 16, 20)     4            4         [0, 4]             [4]
```

* **Root is a candidate** (rows 2–5): `subject` becomes discriminating among candidates, the
  narrowed `TERM_OVERLAP` fires on **every** candidate from the shared subject, `rank`'s
  all-or-none sweep then drops the component entirely, and **the query-aware fill discloses
  nothing** — 12 → 0, 9 → 0, 6 → 0.
* **Root is a hit** (rows 1 and 6): `subject` becomes discriminating among *hits*.
  `plan.hit_ranks` has **no sweep** — it reads `score(...).anchored_value` directly — so every
  hit scores the same nonzero value, and `_top_k_hit_ids`' `(-fill_score, position)` tie-break
  is again the whole selection. Row 6 is the cleanest: on the flat fixture `hit_ranks` returns
  `[0, 4]` (the fix working); with Gmail's own `Re:` it returns `[4]` — **uniform, oldest-K,
  R-DISC-026's exact behaviour restored.**

The fixture that carries the round's DISC-01 evidence names the prefix in prose and does not
carry it:

```python
"""...Gmail puts one subject on every message of a thread - `Re: <subject>` on every reply..."""
subjects=dict.fromkeys(order, subject),      # the identical string on every message
```

`r07_disc01_with_re.py` re-runs the implementer's own six queries over that fixture with and
without the prefix and reports 15/15 in both cases — because at `hit_every=8` the root is a hit,
so the asymmetry lands in the hit pool rather than the fill. The 15/15 number is therefore
correct and does not itself establish the rule, and one row of the hit-placement sweep above is
enough to see it.

**Verdict on Priority 1.** A11's *stated* rule is implemented, generally, over facts. It is
then undone on the shape it was written for by a tokenizer that treats `re` as a content word.
This is R-DISC-031.

### The cliff: where the line falls when a component fires on all-but-one candidate

`r02_cliff.py`. Twenty messages, hits at 0/6/12/18, walking `k` = how many messages' own text
carries the term:

```
    k  candidates carrying  |fill|  |included|
    0                    0       0          11
   ...
   17                   14       9          20
   18                   15       9          20
   19                   15       9          20
   20                   16       0          11

  ids that lost their disclosure between k=19 and k=20:
     002 003 004 008 009 010 014 015 016
```

`rank`'s sweep is `0 < len(reached) < len(pool)`, so k of N admits k for every k in [1, N−1] and
**zero at k = N**. The line is exactly where A11's sentence puts it — "admission requires a
component that separates at least one candidate from another" — so it is principled in the sense
that it is the amendment read literally. It is also **non-monotone in relevance**: making one
more message match the query removes **nine** other matching messages from the disclosure. And
it is undeclared — see R-DISC-035.

`r13_ordering.py`'s last section confirms the same cliff from the other side: when every
candidate fires `TERM_OVERLAP` from its **own** text (a message-level fact, not a thread-level
one), admission is still zero.

---

## Priority 2 — query-aware for queries nobody wrote

My own thread, my own vocabulary, my own queries, driven end to end
(`r03_e2e.py`, `r04_hit_ranks.py`). Twenty-four messages, one subject carrying all five terms,
each message's body carrying the subset its index's bits select (mechanical, not hand-tuned),
`in_reply_to` chained, real `GmailClient` behind `MockTransport`.

**A. The modal Gmail case reframes DISC-01, and nobody has said so.** A term that appears in a
thread's subject matches **every message of the thread in Gmail's own search**:

```
  borogrove    roles={'matched': 24}  depths={'body_clean': 10, 'snippet': 14}  |included|=24
  slithy       roles={'matched': 24}  depths={'body_clean': 10, 'snippet': 14}  |included|=24
  toves        roles={'matched': 24}  depths={'body_clean': 10, 'snippet': 14}  |included|=24
  outgrabe     roles={'matched': 24}  depths={'body_clean': 10, 'snippet': 14}  |included|=24
  mimsy        roles={'matched': 24}  depths={'body_clean': 10, 'snippet': 14}  |included|=24
```

Every message is a hit, so **there are no fill candidates at all** and A11's admission rule is
inert. What decides this response is `hit_ranks` — which 10 of 24 hits keep a body. And:

```
  queries: 5  pairs: 10  pairs whose DEPTH MAP differs: 0
              pairs whose INCLUDED SET differs (DISC-01's own quantity): 0
  protected == the 10 EARLIEST by position?  True, for all five queries
```

**So on the exact thread shape A11's defect paragraph names, driven end to end, DISC-01's
acceptance still fails — 0 of 10 pairs differ — and the protected set is still oldest-K.** Not
because A11 fails, but because on that shape the E4 fill is not what is being asked, and the
thing that *is* being asked (`hit_ranks`) is defeated by R-DISC-031(b).

**B. Where the subject does not carry the terms, the policy is genuinely query-aware.** Same
thread, subject changed to `"quarterly planning discussion"`:

```
  borogrove    |included|=24     slithy   |included|=23     toves  |included|=17
  outgrabe     |included|=10     mimsy    |included|= 9
  queries: 5  pairs: 10  pairs whose included set DIFFERS: 10
```

Ten of ten, for a reason a stranger can read: each message's own body carries a different subset
of the terms. This is real and it is round 25's genuine achievement.

**C. A query whose terms appear in no body but in the subject.** *What should happen*: the
response should either disclose the thread (the term is genuinely about it) or say plainly that
nothing in it was singled out. *What does happen*: Gmail matches the subject, every message
becomes a hit, and all 24 are disclosed at `body_clean`/`snippet` — `|included| = 24`. **That is
honest, and it is honest by accident**: the fill's answer to that query would be "admit nothing"
(`r01` A, `r06` C), and the reason the caller never sees the empty fill is that Gmail's own
matching made the question moot. On a thread reached **structurally** — L1B decomposition, L2
relaxation, L3 broadening, or a sibling source recovered by reply-tree — the hits are not the
whole thread, the fill is what decides the rest, and the empty answer is what the caller gets
with nothing said about it (R-DISC-035).

---

## Priority 3 — the ordering half

`r13_ordering.py`. R-DISC-018's claim was that *the top score class of the E4 ranking is Baseline
F's ±2 window*, so one prefix length is not enough: I swept **every** prefix k, on both the flat
fixture and Gmail's `Re:` shape, for all six of the implementer's queries.

```
  Baseline F(+/-2) selects 10 positions, in its own preference order:
    001 007 009 015 017 002 006 010 014 018

  borogrove          |ranked|=12  prefixes k where the E4 top-k SET equals Baseline F's: [1]
  slithy             |ranked|=12  ... none
  toves              |ranked|=12  ... none
  outgrabe           |ranked|= 7  ... none
  mimsy              |ranked|= 7  ... none
  borogrove+slithy   |ranked|=18  ... none
```

Identical on the `Re:` shape. At no prefix k ≥ 2 does the E4 top-k set equal Baseline F's top-k
set, for any query, on either shape. The two agreements at k = 1 are single-element sets and
carry no information.

**The ordering half of A11 is real, it survives the `Re:` shape, and R-DISC-018 is fixed.** The
key is `(-anchored_value, position)`, `POSITION_ADJACENCY` and `DECISION_CUE` are not in it, and
the implementer's replant R95 isolates that from the admission half. This is the cleanest piece
of work in the round.

---

## Priority 4 — R-DISC-026, and whether `plan.hit_ranks` is real

**At the planner, it is real, and it matches a hand-typed oracle.** `r04_hit_ranks.py` section
D, thread of 32 with hits every 4, query `toves` (= `TERMS[2]`, so bit 2 of the index selects
it):

```
  query_aware_e4             evidence fill_scores = [0, 4]   nonzero on  004 012 020 028
  baseline_f_fixed_window    evidence fill_scores = [0, 4]   nonzero on  004 012 020 028

  hand-typed oracle (positions carrying 'toves' in their own text) = 004 012 020 028
```

Both arms agree, and both match the oracle I typed out from the fixture's construction rule
rather than read off `hit_ranks`.

**It is computed outside the `Selector`.** Every reference in `server/` and `harness/`:

```
  disclosure/plan.py:208  def hit_ranks(thread: ThreadInput, query: QueryFacts) -> Mapping[str, int]
  disclosure/plan.py:344      hits = hit_ranks(thread, query)          <- the only call site
  disclosure/ladder.py:79     (a comment)
```

`hit_ranks` takes no selector, is called once from `plan_thread` outside the `selector.select`
call, and both arms produce identical evidence scores. **DISC-02 remains a comparison of fills.**
The implementer's own caveat that
`test_the_two_arms_sacrifice_evidence_depth_in_the_same_order` is close to structural and is
worth less than its sibling is correct, and stating it was the right call.

**But the fix is half a fix.** `rank` has two guards — the discriminating-facts narrowing **and**
the all-or-none sweep. `hit_ranks` has only the first. On Gmail's `Re:` shape the narrowing
mis-classifies `subject`, the sweep is not there to catch it, and every hit scores the same
nonzero value: oldest-K, in both arms, for every query (`r04` section B, end to end;
`r06` section D and `r08` in isolation). That is R-DISC-034, and it is the mechanism behind
R-DISC-031(b).

`/tmp/rdisc23/p12_scoring_claims.py` re-run on this tree still prints
`distinct evidence fill_scores=[0]` and `protected top-5 == the 5 EARLIEST hits by position?
True` in both arms — consistent with the implementer's stated fallback (that fixture's hits are
separated by nothing), so I do not read it as a regression. `r04` is the probe that decides the
question, because its hits **are** separated and the answer is still oldest-K on the real shape.

---

## Priority 5 — Part 3: the estimate and the wire, and the host's cap

This is the item OD-7 point 3 names, and what I found is larger than what the report measured.

### The estimate is not an upper bound on the wire, in its own token unit

`r11_break_bound.py`, `r12_unmeasured.py`. The round's headline property is stated once in
`envelope/measure.py` and asserted by
`test_the_estimate_is_an_upper_bound_on_the_rendered_wire`:

> the estimate the ceiling is enforced against is an upper bound on the rendered response, in
> the same whitespace-token unit.

Holding the thread at 400 messages and varying **only the number of distinct senders** — the
shipped path, the shipped ceiling, `render()` as the client receives it:

```
   senders  estimate  wire_tok  wire/est    chars  bound
         1      3515      3070     0.873    26000  holds
         2      3515      3085     0.878    26168  holds
         5      3515      3130     0.890    26672  holds
        10      3515      3205     0.912    27512  holds
        25      3515      3430     0.976    30047  holds
        50      3515      3805     1.083    34272  *** OVER ***
       100      3515      4555     1.296    42722  *** OVER ***
       200      3515      6055     1.723    59722  *** OVER ***
       400      3515      9055     2.576    93722  *** OVER ***
```

The bound breaks at **50 distinct senders on a 400-message thread**, and is at 0.976 — no
margin at all — by 25. Worst measured, with long addresses, twenty recipients, attachments and
long subjects: **11.46×** (`r11`, 1000 messages).

**Where the tokens are.** `r12` section B, 400 messages / 400 senders:

```
  measure_tokens(envelope)           : 3515
  RESPONSE_STRUCTURAL_TOKENS (flat)  :  500
  charged for rows                   : 1710
  rendered structuredContent tokens  : 8290

  Inside sources[0], by rendered tokens:
    participants                    6815 tokens      76855 chars
    messages                         884 tokens       6120 chars   <- charged per row
    collapsed_runs                   409 tokens       4513 chars
```

**`Source.participants` is 82 % of the rendered response and `measure_tokens` charges nothing
for it.** `RESPONSE_STRUCTURAL_TOKENS`'s own docstring enumerates what the flat 500 covers —
"`retrieval_report`, `asked_for`, `scan_scope`, `counters`, `ceiling`, `budget`, the freshness
stamps and the mirror's own header and residue lines" — and `participants` is not in that list.
It is a **per-source** field whose size scales with the number of distinct addresses in the
thread, and it is charged in neither `measure_tokens` nor `layout_tokens`. There is no cap on it
anywhere in `server/src`.

**Why the round's test could not see this.** `_long_thread`, the fixture behind the six
parameterised sizes, uses `sender="alpha@team.example"` and `to=("ops@team.example",)` for
*every* message, so `participants` has exactly two entries at 5 messages and at 400. The test
varies **size** across six values and holds every other shape property constant — one sender,
one recipient, six-token bodies, and a uniform `"Re: quarterly cadence"` subject on index 0 as
well as on the replies, so it does not exhibit the root asymmetry either. That is the project's
own named recurring defect — *one shape validated, peers trusted* — sitting in the test that
certifies the round's central Part 3 claim. R-DISC-036.

I record that this is the peer the implementer told a reviewer to attack first, and that the
attack succeeds for a reason the implementer did not name: not a longer row, but a field that is
not a row.

### The ceiling does not bound the rendered form in the host's unit, and the response says it is complete

`r15_mcp_wire.py`, measured on the **`CallToolResult` a client is handed** — `call(service,
"mailweave_search", …)`, `structured_content` serialised plus the text content beside it, which
is what `anthropic/maxResultSizeChars` counts:

```
   msgs  senders  declared   json_ch   text_ch     TOTAL   x cap  verdict
      3        1      9000      6493      2963      9456    0.38  ok
      5        1      9000      8977      4357     13334    0.53  over warning
      8        1      9000     12705      6448     19153    0.77  over warning
     10        1      9000     15193      7844     23037    0.92  over warning
     12        1      9000     16902      8456     25358    1.01  OVER CAP
     15        1      9000     19464      9374     28838    1.15  OVER CAP
     20        1      9000     23734     10904     34638    1.39  OVER CAP
     40        1      9000     40814     17024     57838    2.31  OVER CAP
     60        1      9000     46373     13327     59700    2.39  OVER CAP
    400        1      9000     22287      4506     26793    1.07  OVER CAP
    400      400      9000     88014      4506     92520    3.70  OVER CAP
```

**The line is at twelve messages, not sixty.** The implementer's report names a 60-message reply
at 68,363 characters and assigns the whole issue to PF-6's figure. My measurement puts an
ordinary **twelve-message** thread of ~110-word messages at 25,358 characters — 1.01× the
[VERIFIED] 25,000-character cap — and the 10,000-character warning is crossed at **five
messages**. A twelve-message thread is not a large-response edge case; it is the median business
email conversation and it is what the OD-7 demonstration will be pointed at.

**And this is the half that is not PF-6's figure.** What that 25,358-character response says
about itself:

```
  truncated_by         : None
  partial              : False
  withheld             : 0 records
  not_included_sources : 0
  ceiling              : {'normal': 9000, 'applied': 9000, 'why': None}
  source.stated_total  : 12
  source.included      : 12
  source.completeness  : as_reported_by_source
  source.withheld_here : []
```

The response asserts that it is **complete, untruncated, and comfortably inside its own budget**,
and the host then cuts it. The model receives a truncated thread with no marker, no withheld
record, and an `included: 12 of 12` claim about messages it never saw. **That is issue #296's
shape — a thread returned with content missing and no truncation marker — produced by MailWeave
itself**, which is the failure this project exists to prevent, and it is what `PRODUCT_CONTRACT`
C-06 and OD-3's branch (ii) ("being truncated by the host instead of by us is a defect we forbid
elsewhere") both forbid.

Grepping the whole of `server/src` for `maxResultSizeChars` returns **nothing**. There is no
character-unit measure anywhere in the system, so nothing could have caught this. The *figure*
9,000 is `[DESIGN, set by PF-6]` and I agree it is PF-6's to move; the *absence of any bound in
the unit the host enforces*, and the response's positive claim of completeness while over it,
are not a figure and are not PF-6's.

### A degradation step never makes the response larger — A11's second rule holds

`/tmp/rdisc23/p08_step1_inflates.py` re-run on this tree:

```
  STUB_ROW_TOKEN_ESTIMATE       : 120
  row at snippet depth costs    : 180
  SAME row degraded to stub cost: 120
  layout cost before the ladder : 56300  (ceiling 9000)
    step 1 e4_query_scored_fill   56300 -> 37880
    step 5 hit_thread_stub_runs   37880 ->  2081
  ladder returned
```

Round 23 measured step 1 taking 9,300 → 27,270 and then refusing. It now shrinks, monotonically,
and the ladder returns. **R-DISC-019 is fixed**, and `r10` section C confirms it end to end at
five ceiling settings. `assert_cost_did_not_rise` covering every step but step 6 is the right
shape: it covers a rung nobody has written yet.

### R-DISC-020 is fixed

`r15` section B. The shape that raised `DisclosureLadderExhausted` out of `assemble` now reaches
a client as a declared in-band result:

```
  n= 700 budget= 620  isError=True  keys=['code', 'declined', 'remediation', 'retry_with']
      -> declined: budget_exhausted
         remediation: the A.9a ladder ran every published step and the response is still
         ~4415 whitespace tokens against a declared ceiling of ...
```

It is still an exception out of `assemble` itself (`/tmp/rdisc23/p23_step1_wire.py` re-run), but
the tool handler catches it and the caller gets a code, a reason and an executable retry. That
satisfies what R-DISC-020 asked for.

---

## Priority 6 — Part 4: the floor, and its oracle

**I planted round 23's defect back and the hand-written oracle caught it as an oracle.**

`/tmp/rdisc25/plant_floor`, a whole-tree copy with `docs/`, all three packages asserted resolving
inside it before the plant ran. The plant restores the one line round 23 had:

```python
            member = members.get(member_id)
            if member is None:
                continue
            if member_id in hits:      # R-DISC PLANT: round 23's skip, restored
                continue
```

Full suite on the plant tree — three tests red, nothing else:

```
FAILED tests/test_round25.py::test_the_floor_is_what_the_reply_tree_says_it_is
FAILED tests/test_round25.py::test_a_hit_that_is_another_hits_floor_member_is_never_withheld
FAILED tests/test_replants.py::test_every_behaviour_these_rounds_changed_fails_a_test_when_it_is_removed
```

The oracle test fails **against the typed-out tuple**, naming exactly the two messages round 23
dropped:

```
>       assert computed == ORACLE_FLOOR
E       AssertionError
E         Extra items in the right set:
E         'h-004'
E         'h-003'
```

`h-003` and `h-004` are the two hits that are each other's parent and child — the case
R-DISC-021 filed. **The oracle disagreed with the implementation**, which is the property round
23's sixteen plants could not have had, because every one of them compared the payload with
`floor_of`'s own output.

The second failure comes through the **driver-level gate**, not through a test's own arithmetic:

```
FloorMembershipLost: A.9a step 8 (withheld_record) removed ['c-002', 'c-004'] from the payload
while the evidence message(s) they hang off are still disclosed...
```

`Layout.floor_pairs` naming *whose* floor each member is, and `assert_floor_intact` reading the
pairs so it can distinguish the one lawful removal (a whole declared source split) from every
other, is the right structure for A12.3's reading of OD-3. **Part 4 is done properly.**

---

## Priority 7 — the four open findings, judged under OD-7

All four reproduce exactly as filed. I ran each rather than reading the table.

| Finding | Reproduced by me | OD-7 ruling |
|---|---|---|
| **R-DISC-024** — the promotion rule's three clauses | `p09`: a one-word `thanks` parent **and a parent with no observed text at all** are both promoted, so clause 1 is `relation is PARENT` in disguise. `p10`: `constraint_carrier occurrences: 0` across every shipped-path run | **Track.** Nothing false reaches the wire: the row states the relation it has and the depth it has. Clause 3 is a vocabulary member with no producer, which is a claim wider than the code but not an untrue statement about a response. Clause 1 needs A7 span provenance in `MemberFacts` — a design change in a rule OD-3 names, and not an implementer's |
| **R-DISC-025** — promotion decides a label, not a depth | `r14`: `FLOOR_BASE_DEPTH = snippet`, `FLOOR_PROMOTED_DEPTH = body_clean`, but `depth_for` can only reach `body_clean` where a body was **fetched** and T-CD3 forbids disclosure fetching. `p11`: a promoted parent and an unpromoted child are both at `snippet`; `FloorPromoted` is the only difference in the payload | **Track.** The reviewer's two options are "build the budgeted fetch" (WS-10's accountant, forbidden here) or "state it in OD-3's terms" (the owner's sentence). Neither is available before the demo, and the label is not false — it names the relation, not a depth that was reached |
| **R-DISC-028** — silent depth demotions | `r14`: at a binding ceiling, **zero** rows carry any reduction record, no `depth_reduced` kind exists on the wire, and `truncated_by = mailweave`. `p13`: `body_clean → snippet` drops ~1,150 tokens with no record and no size count | **Track**, with a caveat. DISC-03's "silent reductions: 0" is not true today. But each row **declares its own depth** from the closed vocabulary and carries an executable `unabridged` affordance (`p22`: 100 % on non-stub rows), so a model can tell it has a snippet and can fetch the rest. What is missing is the size count, which is a rubric-acceptance gap, not a safety one. It needs a new reduction kind and a response-level step block — an A12-shaped wire change |
| **R-MCP-012** — `segment` is inert | `r14`: `segment` is published in `surface/tools.py` with a described meaning; `p21`'s twelve calls return the identical whole map | **Track.** R-MCP's finding, not mine, and I concur with the stated reason: implementing it is WS-16's and removing it needs an A12 entry. A published argument that does nothing is a claim wider than the code; it is not a false statement about a response that was returned |

---

## Priority 8 — what survived round 23, and still does

| Survival | Verdict |
|---|---|
| **Driver-level floor gates with real plants** | **Survives, and is stronger.** My plant turned two behavioural tests red plus the manifest meta-test, one of them through the gate itself rather than through a test's arithmetic. `floor_pairs` makes the gate relative and it fails closed when the pairs are empty |
| **The single `Selector`** | **Survives.** `def select(self` is defined in exactly one file, `disclosure/plan.py`. `FixedWindow().radius` is still `E4_ADJACENCY_POSITIONS`. `hit_ranks` is selector-independent and both arms produce identical evidence scores (`r04` D), so the one object the arms differ in is still the one object |
| **`layout.cost() == measure_tokens(envelope)`** | **Survives.** `/tmp/rdisc23/p19_measure_equality.py` re-run: delta **0** on all five shapes from 5 to 600 messages. `r14` confirms `measure_tokens(env) <= ceiling.applied` on the shipped path at seven sizes. The property is intact — it is the *quantity* both sides agree on that does not bound the wire (R-DISC-032) |
| **The published weights did not move** | **Survives.** `E4_WEIGHTS` is byte-identical; A11 added no number |
| **EV-03's record discipline** | **Survives.** `p05`, `p06`, `p18`, `p22` re-run: `disclosed MATCHED rows whose A.9(2) floor member is not present: 0` at every band size; `Source` still forces three dispositions per position; `accounted_ids` still covers every mapped member |

---

## Findings

| ID | Severity | Reachability | **Fix before demo?** | One line |
|---|---|---|---|---|
| **R-DISC-031** | HIGH | REACHABLE today, end to end, shipped defaults. Every Gmail thread of more than one message | **YES** | `content_tokens` keeps `re`, so the `Re:` prefix makes `subject` message-discriminating and A11 stops applying to the fact it was written about |
| **R-DISC-032** | HIGH | REACHABLE today, shipped path and ceiling. Breaks at 50 distinct senders on a 400-message thread; no margin at 25 | **YES** | `measure_tokens` charges nothing for `Source.participants`, which is 82 % of the wire, so the estimate is not an upper bound on the response in its own token unit |
| **R-DISC-033** | HIGH | REACHABLE today at the MCP tool surface, shipped defaults. Threshold **12 messages**; the 10 k warning at 5 | **YES** | The rendered `CallToolResult` crosses the host's 25,000-char cap while declaring `truncated_by: null`, `partial: false`, `withheld: []`, `included: 12 of 12`. No character measure exists anywhere in `server/src` |
| **R-DISC-034** | MEDIUM | REACHABLE today. Any thread where an admitting component anchors on every hit | **YES**, as part of 031 | `hit_ranks` lacks `rank`'s all-or-none sweep, so a uniform nonzero score makes the position tie-break the whole selection — oldest-K, which EV-02's guard names by construction |
| **R-DISC-035** | MEDIUM | REACHABLE today at the planner; end to end on any structurally-reached or sibling thread | no — **track** | A11's admission is a step function at k = N: one more matching message removes nine others, and "nothing relates" and "everything relates" render identically |
| **R-DISC-036** | LOW | N/A — a property of the suite, established by executing 032's counterexample against it | no — **track**, but fix with 032 | The test certifying the round's headline Part 3 property varies size across six values and holds every other shape property — including the one that dominates the wire — constant |
| R-DISC-024 | MEDIUM | REACHABLE (`p09`, `p10`) | no — **track** | Promotion clause 1 is `relation is PARENT` in disguise; clause 3 has no producer. Carried forward unchanged |
| R-DISC-025 | MEDIUM | REACHABLE (`p11`, `r14`) | no — **track** | Promotion decides a label, not a depth. Carried forward unchanged |
| R-DISC-028 | MEDIUM | REACHABLE (`p13`, `r14`) | no — **track** | A depth demotion leaves no reduction record and no size count; DISC-03's "silent reductions: 0" is not true |
| R-MCP-012 | LOW | REACHABLE (`p21`, `r14`) | no — **track** | `segment` is published and inert. R-MCP's finding; I concur with its stated reason |

```
ID:            R-DISC-031
Severity:      HIGH
Reachability:  REACHABLE today, end to end, shipped defaults. Modal case: any Gmail thread of
               more than one message, because Gmail sends `Subject: S` on the root and
               `Re: S` on every reply.
Fix before demo? YES. It restores a degenerate strategy EV-02 names by construction (oldest-K)
               on the shape the live demonstration will use, and it makes the OD-7 point-4
               comparison measure a policy that did not fire. A comparison run against the
               native connector that concluded anything about the query-aware thesis would be
               concluding it from a run in which the thesis was inert.
Rubric:        DISC-01 (its acceptance and its guard), DISC-02 (the arm being compared),
               EV-02 (its second degenerate-strategy guard, R-RETR's criterion).
Location:      server/src/mailweave/disclosure/weights.py, `fact_values` - tokenises
                 `candidate.subject` through `content_tokens`, which keeps `re` as a content
                 token; the docstring asserts the opposite.
               server/src/mailweave/disclosure/weights.py, `message_discriminating_facts` -
                 therefore classifies `subject` as message-discriminating whenever the pool
                 holds the thread root and at least one reply.
               server/src/mailweave/query/analysis.py, `content_tokens` - `re` is not a
                 stopword.
Repro:         /tmp/rdisc25/r06_re_prefix.py
                 content_tokens('S') -> 7 tokens; content_tokens('Re: S') -> 8;
                 symmetric difference ['re']
                 Gmail's shape: discriminating = ['subject']; flat subject: []
               /tmp/rdisc25/r08_root_message.py - shared_subject_thread(24), query `toves`:
                 hits (1,9,17): |fill| 12 (flat) -> 0 (Re:)
                 hits (2,10,18): |fill| 12 -> 0     hits (3,11,19): 9 -> 0
                 hits (4,12,20): |fill|  6 -> 0
                 hits (0,4,8,12,16,20): hit_ranks [0,4] (flat) -> [4] (Re:)
               /tmp/rdisc25/r04_hit_ranks.py - end to end, five queries on one 24-message
                 thread: depth maps differ in 0 of 10 pairs; protected top-10 == the 10
                 earliest by position, for every query.
Expected:      A11: "A component that fires identically on every candidate of a thread ranks
               but does not admit on that thread, whatever its published weight." The subject
               is the fact A11's own defect paragraph is about.
Actual:        The subject is readmitted as a discriminating fact by a two-character prefix,
               and A11 stops applying to it. Two opposite consequences: the fill collapses to
               zero where the root is a candidate; the hit ranking goes uniform and reverts to
               oldest-K where the root is a hit.
Required fix:  Make the subject fact comparable in the form the components read it, which is
               what `fact_values`' docstring already claims. The narrow repair is to strip the
               reply/forward prefixes when tokenising the subject fact - Gmail's own
               `Re:`/`Fwd:`/`Fw:` and the localised forms - inside `fact_values` only, leaving
               the published score and the row's reason untouched. Then assert it: a fixture
               whose subjects differ ONLY by the prefix must produce `subject` NOT in
               `message_discriminating_facts`. Note this fix alone does not close
               R-DISC-034, and a `Re:`-carrying fixture must replace the flat one in
               `shared_subject_thread` and in `_long_thread` so the shape cannot regress.
```
```
ID:            R-DISC-032
Severity:      HIGH
Reachability:  REACHABLE today, shipped path, shipped ceiling, no override. Breaks at 50
               distinct senders on a 400-message thread; 0.976 (no margin) at 25.
Fix before demo? YES. The estimate is the only thing standing between a response and the host,
               and it is not an upper bound on the quantity it claims to bound. Every
               downstream statement that rests on it - `ceiling.applied`, `truncated_by`,
               DISC-06's whole mechanism - rests on a number that can be 2.6x low on an
               ordinary mailing-list thread and 11x low on a large one.
Rubric:        DISC-06 (its mechanism), DISC-04 (the units of its ratio), PART-05 (its guard).
Location:      server/src/mailweave/envelope/measure.py, `measure_tokens` - charges
                 RESPONSE_STRUCTURAL_TOKENS + per-row + per-collapsed-run + per-withheld-record
                 and nothing else.
               server/src/mailweave/envelope/measure.py, `RESPONSE_STRUCTURAL_TOKENS = 500` -
                 a flat per-RESPONSE constant whose docstring enumerates what it covers, and
                 `participants` is not in that list.
               server/src/mailweave/disclosure/layout.py, `layout_tokens` - the same omission,
                 which is why the two measures still agree.
               server/src/mailweave/envelope/wire.py:880 `participants` - a per-SOURCE tuple
                 with no cap anywhere in server/src.
Repro:         /tmp/rdisc25/r12_unmeasured.py - 400 messages, sender count varied, all else held:
                 senders   1 -> wire/est 0.873     senders  25 -> 0.976
                 senders  50 -> 1.083 *** OVER *** senders 400 -> 2.576 *** OVER ***
                 field census at 400/400: participants 6815 tokens / 76855 chars, of 8290
                 rendered structured tokens; measure_tokens = 3515, of which rows = 1710.
               /tmp/rdisc25/r11_break_bound.py - worst measured ratio 11.460 (1000 messages,
                 short bodies, 30 recipients, long addresses, long subjects).
Expected:      envelope/measure.py: "the estimate the ceiling is enforced against is an upper
               bound on the rendered response, in the same whitespace-token unit", asserted by
               test_the_estimate_is_an_upper_bound_on_the_rendered_wire.
Actual:        False for any thread with more than ~25 distinct participants, on the shipped
               path, at the shipped ceiling.
Required fix:  Charge every wire field whose size scales with the response, not only the rows.
               `participants` is the one that dominates and it is per-source, so the minimum is
               a per-source structural charge plus a per-participant charge, added to BOTH
               `measure_tokens` and `layout_tokens` so `layout.cost() == measure_tokens` is
               preserved. Then re-derive the constants against a fixture matrix that varies
               shape as well as size (see R-DISC-036), and consider capping `participants` with
               a declared count, which is cheaper than charging an unbounded list.
```
```
ID:            R-DISC-033
Severity:      HIGH
Reachability:  REACHABLE today at the MCP tool surface, shipped defaults, no override.
               Threshold: 12 messages of ~110 words. The host's 10,000-char warning is crossed
               at 5.
Fix before demo? YES, and this is the one OD-7 point 3 names. A response the host silently
               truncates is a response that lost evidence with no withheld record - and this
               one positively asserts it is complete while it happens.
Rubric:        DISC-06 (its acceptance, "Responses truncated by the host: 0 [DEFINITIONAL]"),
               PART-01, PART-02 (the included set matches the payload - in the host's frame it
               does not), EV-03 (nothing dropped without a record).
Location:      server/src/mailweave/envelope/measure.py - the ceiling is enforced in
                 whitespace tokens; no character measure exists. `grep -rl maxResultSizeChars
                 server/src` returns NOTHING.
               server/src/mailweave/disclosure/ladder.py, `Ceilings` - both published figures
                 are token figures.
               server/src/mailweave/surface/server.py, `call` - hands the CallToolResult over
                 with no size check in the unit the host enforces.
Repro:         /tmp/rdisc25/r15_mcp_wire.py - CallToolResult chars (structured_content
                 serialised + text content), host cap 25,000 [VERIFIED] per AD PF-6:
                    5 msgs -> 13,334 (over the 10k warning)
                   10 msgs -> 23,037 (0.92x cap)
                   12 msgs -> 25,358 (1.01x)   <- the line
                   20 msgs -> 34,638 (1.39x)
                   40 msgs -> 57,838 (2.31x)
                  400 msgs -> 26,793 (1.07x);  400 msgs / 400 senders -> 92,520 (3.70x)
               And what the 12-message response says about itself:
                  truncated_by: None      partial: False      withheld: 0 records
                  ceiling: {normal: 9000, applied: 9000, why: None}
                  source.stated_total: 12   source.included: 12   withheld_here: []
Expected:      AD PF-6; OD-3 branch (ii) "being truncated by the host instead of by us is a
               defect we forbid elsewhere"; PRODUCT_CONTRACT C-06; DISC-06's [DEFINITIONAL] 0.
Actual:        An ordinary twelve-message thread is handed to the host over its cap, declaring
               itself complete and untruncated and 0% over a budget it says it is inside. The
               model receives a truncated thread with no marker and an `included: 12 of 12`
               claim about messages it never saw. That is issue #296's shape, produced by
               MailWeave.
Required fix:  Two parts, and only the second is PF-6's.
               (1) NOT PF-6's, and needed before the demo: the response must be bounded in the
               unit the host enforces, and must never assert completeness while over it. The
               ladder decides before there is anything to serialise, so the honest minimum is a
               post-render check in `call`: measure the rendered CallToolResult in characters
               against a published host-cap constant, and if it is over, re-run the ladder at a
               lowered ceiling and declare the reduction (`truncated_by: mailweave`, a
               `ceiling.why` naming the host cap, and withheld records for anything dropped).
               A response that cannot be brought inside must decline in band, as
               DisclosureLadderExhausted already does, rather than be handed over.
               (2) PF-6's: the 9,000 and 12,000 token figures re-derived from the measured cap.
               R-DISC-032 must be fixed first, or (2) will be derived against a quantity that
               is not an upper bound on anything.
```
```
ID:            R-DISC-034
Severity:      MEDIUM
Reachability:  REACHABLE today. Any thread where an admitting component anchors on every hit.
Fix before demo? YES - as part of R-DISC-031's fix, and not separately. On its own it is a
               design asymmetry; combined with R-DISC-031 it is what restores oldest-K. Fixing
               only R-DISC-031 leaves the asymmetry live for the next fact that goes uniform.
Rubric:        EV-02 (its second guard), DISC-01, DISC-02.
Location:      server/src/mailweave/disclosure/plan.py, `hit_ranks` - reads
                 `score(...).anchored_value` directly.
               server/src/mailweave/disclosure/weights.py, `rank` - the all-or-none sweep
                 (`0 < len(reached) < len(pool)`) that `hit_ranks` does not have.
Repro:         /tmp/rdisc25/r06_re_prefix.py section D - Gmail's shape, 12 hits:
                 anchored_value per hit = [4,4,4,4,4,4,4,4,4,4,4,4]; distinct = [4]
                 -> position is the whole selection
               /tmp/rdisc25/r04_hit_ranks.py section B - end to end, five queries:
                 protected == the 10 EARLIEST by position? True, five times out of five.
Expected:      ladder.py `DISCLOSURE_TOP_K_HITS`: the protected hits are "decided by the
               published E4 score, ties by thread position. Deliberately not by recency and not
               by arrival order."
Actual:        Arrival order, whenever the query anchors on every hit equally - which the
               shared subject guarantees on the modal thread. R-DISC-026 is fixed where the
               hits' own text differs in the term and not otherwise.
Required fix:  Apply A11's second guard where A11's first guard is applied. `hit_ranks` should
               run the same all-or-none sweep `rank` does, so a component anchored on every hit
               ranks nothing - which returns the pool to a stated zero and position, rather than
               to a uniform nonzero that looks like a score. State one rule in one place and
               call it from both, so a third pool added later inherits it.
```
```
ID:            R-DISC-035
Severity:      MEDIUM
Reachability:  REACHABLE today at the planner and end to end on any thread reached
               structurally (L1B/L2/L3) or as a sibling source.
Fix before demo? NO - track. Nothing false reaches the wire and nothing is lost without a
               record: the un-admitted messages are present as stub rows or declared
               collapsed-run members with executable affordances, and membership holds. It is a
               usefulness and explainability defect, not a truthfulness one.
Rubric:        DISC-01 ("Identical output for materially different queries: flagged and
               investigated"), DISC-03.
Location:      server/src/mailweave/disclosure/weights.py, `rank` - the sweep is
                 `0 < len(reached) < len(pool)`, a step function at k = len(pool).
               server/src/mailweave/envelope/wire.py - no field records that a component was
                 dropped for firing on every candidate.
Repro:         /tmp/rdisc25/r02_cliff.py - 20 messages, hits at 0/6/12/18, walking k:
                 k=19 (15 of 16 candidates carry the term): |fill|=9,  |included|=20
                 k=20 (16 of 16 carry it):                  |fill|=0,  |included|=11
                 ids that lost disclosure: 002 003 004 008 009 010 014 015 016
               /tmp/rdisc25/r09_wire_honesty.py section C - "no message's text carries the
                 term" and "every message's text carries it" produce the same |fill| (0) and
                 the same |included| (11).
Expected:      A11's rule is a defensible reading; a caller should be able to tell why the fill
               is empty.
Actual:        Making one more message match the query removes nine other matching messages
               from the disclosure, and the response cannot distinguish "nothing in this thread
               relates to your query" from "everything in it does, so none was singled out".
               Those are opposite facts rendered identically.
Required fix:  Declare it. A response-level or per-source field stating that an admitting
               component fired on every candidate and therefore admitted none - the same shape
               `NotTriedWhy` already has for rungs. That is a wire-vocabulary addition and
               belongs to the round that owns the surface, so it is filed rather than demanded
               now. Whether the cliff itself should be softened (admit on the published score
               when no component separates, rather than admitting nothing) is a policy question
               for the owner, because it trades A11's honesty for coverage.
```
```
ID:            R-DISC-036
Severity:      LOW (as a defect); the reason two HIGH findings were invisible
Reachability:  N/A - a property of the test suite, established by reading and by executing
               R-DISC-032's counterexample against it.
Fix before demo? NO - track, but fix it in the same edit as R-DISC-032, because otherwise the
               repaired constants will be re-derived against the same single shape.
Rubric:        none directly; AGENT_LOOP's anti-gaming discipline and the round's own
               reintroduction rule.
Location:      tests/test_round25.py:816 `_long_thread` - sender="alpha@team.example" and
                 to=("ops@team.example",) for every message at every size, body_tokens=6,
                 subject "Re: quarterly cadence" on index 0 as well as on the replies.
               tests/test_round25.py:837 `test_the_estimate_is_an_upper_bound_on_the_rendered_wire`
                 - parametrised over [5, 20, 60, 120, 240, 400], i.e. over SIZE only.
               tests/test_disclosure_round23.py:304 `shared_subject_thread` - docstring names
                 the `Re:` prefix, `subjects=dict.fromkeys(order, subject)` omits it.
Repro:         /tmp/rdisc25/r12_unmeasured.py - the field that dominates the wire is constant
                 at 2 entries across all six parameterised sizes.
               /tmp/rdisc25/r08_root_message.py - the fixture's own docstring's `Re:` case
                 inverts three of its results.
Expected:      The project's own stated discipline: "one shape validated, peers trusted" is
               named in tests/test_lexical_ladder.py's header as this codebase's recurring
               defect.
Actual:        The test that certifies the round's headline Part 3 property varies one
               dimension and holds every other constant, including the one that dominates the
               quantity being bounded. The fixture that carries the round's DISC-01 evidence
               names the shape it omits.
Required fix:  Vary shape, not only size: distinct-sender count, recipient-list length,
               attachment presence, subject length, and the `Re:` prefix, as a matrix rather
               than a list. Two of those turn a passing assertion red today.
```

---

## Verdict per degenerate-strategy guard

| Guard | Verdict |
|---|---|
| **DISC-01** — *"vary output randomly"; ruled out by requiring each inclusion's reason to name a mechanism traceable to the query* | **DEFEATED, in the same direction as round 23 and by a different mechanism.** Where the query's terms live only in each message's own text the policy is genuinely query-aware — 10 of 10 pairs differ end to end (`r03` B), and the ordering is not the ±2 window at any prefix (`r13`). But on the thread Gmail actually sends, driven end to end, five materially different queries produce **0 of 10** differing included sets and **0 of 10** differing depth maps (`r04` A), because the `Re:` prefix defeats A11 (R-DISC-031). Round 23's guard failure was "one representation for six queries"; round 25's is the same sentence with a new cause. |
| **DISC-02** — *"give the query-aware arm a larger budget"; ruled out by the equal-budget requirement asserted from measured tokens* | **HELD structurally; the measured quantity is worse than round 23 thought.** One `Selector`, one planner, one ladder, one estimate, one ceiling, and `hit_ranks` deliberately outside the selector so both arms sacrifice evidence depth identically (`r04` C/D) — that is a real improvement on round 23 and it should be recorded. But the "measured tokens" the guard rests on are **not an upper bound on the response** (R-DISC-032), and the error scales with participant count, which is a property of the thread rather than of the arm. The guard holds; the acceptance it guards is still not satisfiable. |
| **DISC-03** — *"never strip anything, so nothing needs declaring"* | **HELD.** The ladder strips and `truncated_by` is still refused without an artifact. The opposite failure persists: `body_clean → snippet` leaves no record and no size count, and no `depth_reduced` kind exists (`r14`, `p13`) — R-DISC-028, unchanged. |
| **DISC-04** — *"return stubs only and disclose nothing"; ruled out by EV-02/EV-06 recall bars on the same run* | **NOT TESTABLE HERE.** The bars are `[INHERITED — EP §13.4]` and the pinned tokenizer is at G0. Round 23's note that the degenerate strategy was accidentally *more expensive* than the honest one is now closed: a stub row costs `ROW_STRUCTURAL_TOKENS` and a snippet costs that plus its text, so the ladder is monotone (`p08`). The ratio's units changed again this round and R-DISC-032 invalidates them for any comparison with a host budget. |
| **DISC-05** — *"add levels because they look sophisticated"; ruled out by requiring the comparison to exist before the level ships* | **NOT SATISFIED, unchanged.** The segment level ships behind `mailweave_thread_map(segment=…)` and the comparison does not exist. Worse than round 23 in one respect: `segment` is **inert** (R-MCP-012, reproduced) — the level ships, the comparison does not exist, and the argument does nothing. Its boundary fell from 225 to 75 because it is derived from the per-row charge, which is the right direction and is still computed in the units R-DISC-032 invalidates. |
| **DISC-06** — *"set the ceiling so low that nothing useful is ever returned"* | **HELD on its own terms; the inverse failure is now precisely located and is worse than reported.** 9,000 tokens is not a starving ceiling. But the ceiling is enforced against a quantity that is not an upper bound on the wire even in its own unit (R-DISC-032), the rendered form crosses the host's cap at **twelve messages** rather than sixty, and the over-cap response asserts `truncated_by: null`, `partial: false`, `withheld: 0`, `included: 12 of 12` (R-DISC-033). The one clear repair: a degradation step can no longer enlarge the response (R-DISC-019, fixed), and the ladder's failure mode is now a declared in-band refusal rather than an unhandled exception (R-DISC-020, fixed). |
| **PART-05** — *"emit a map so large it dominates the budget"; ruled out by DISC-04's token ceiling, which counts map tokens* | **PARTIALLY REPAIRED, still defeated in the host's unit.** Round 23: a 600-row map measured 8,300 tokens and rendered 702,915 characters. Now a 400-row map measures 3,515 tokens of 9,000 — it no longer dominates the token budget, and stub rows and collapsed runs are both charged — but it renders **26,793 characters**, still over the cap, and 92,520 with 400 distinct senders. The map is bounded in the unit that is measured and unbounded in the unit that binds. |
| **EV-03** — *"never drop anything (dump)"; inverse: "label everything withheld"* | **HELD, both directions, and strengthened.** Steps 7 and 8 drop and record; `withheld := H − disclosed` is derived by the ledger and refused by `Envelope` if the emitted list disagrees; `Source` forces three dispositions per position; `assert_nothing_vanished` covers every accounted id (`p05`, `p06`, `p18`, `p22` re-run — 0 A.9(2) holes at every band size). `WITHHELD_RECORD_TOKENS` now charges the records, so steps 7 and 8 are no longer free. **One caveat that is not EV-03's fault:** when the host truncates (R-DISC-033), evidence is lost with no withheld record — the discipline is intact and the response never reaches the reader intact. |

---

## Recommendations, per criterion I own

Scoped, every one. **I recommend no transition to PASS anywhere, and no transition to FAIL
either** — the criteria I own are `NOT TESTED` and the evidence I have is reproduction, not the
registered measurement each acceptance names. Where I can decide a criterion in the negative
today I say so, and I say it as a recorded reproduction rather than as a mark.

**DISC-01 · Output is conditioned on the query · M**
**Recommendation: leave NOT TESTED, and record two reproductions against it — one in each
direction.** *Established in the affirmative:* on a thread whose query terms live in each
message's own text, five materially different queries produce **10 of 10** differing included
sets end to end (`r03` B), each inclusion carries a reason naming a query-derived mechanism, and
the ranking is not Baseline F's window at any prefix (`r13`). That is real and it is new this
round. *Established in the negative:* on the thread Gmail actually sends, driven end to end,
five materially different queries produce **0 of 10** differing included sets and **0 of 10**
differing depth maps (`r04` A) — R-DISC-031. *My evidence covers* constructed multi-query threads
at the planner and end to end through the real client; it does **not** cover F17, which the
Verify clause also requires and which needs WS-16. The `[UNSET]` pair-difference threshold is
still unregistered; 10/10 passes any threshold and 0/10 fails any threshold above zero, so the
criterion is decidable today in *both* directions depending on the thread shape — which is
itself the finding.

**DISC-02 · Query-aware policy vs fixed window at equal budget · M**
**Recommendation: leave NOT TESTED, and record the structural achievement without recording the
criterion.** *What I can establish:* the two arms run through one planner, one floor, one
promotion rule, one ladder, one ceiling and one estimate, differing in exactly one object; and
round 25 closed the one leak round 23 left, by putting `hit_ranks` **outside** the `Selector` so
both arms sacrifice evidence depth in the same order (`r04` C/D, verified against a hand-typed
oracle and by enumerating every call site). I attacked it and could not make the baseline lose
unfairly. *What I cannot establish:* the comparison itself (WS-16), the budget–recall curve, and
the equal-*budget* premise — which is now equality in a quantity that is not an upper bound on
the response and whose error scales with participant count (R-DISC-032). Note also that on
Gmail's own shape the shipped arm currently fills **fewer** rows than Baseline F (`p21` re-run:
shipped 0, baseline 9), which is the inverse of round 23's inversion and is R-DISC-031.

**DISC-03 · Depth vocabulary and declared reductions · M**
**Recommendation: leave NOT TESTED, with the two halves separated exactly as round 23 separated
them.** *Established by execution:* 100 % of disclosed rows carry a depth from the closed set and
100 % of non-stub rows carry an executable `unabridged` affordance (`p22`, over a shipped-path
response). *False on execution, unchanged:* "silent reductions: 0" — a `body_clean → snippet`
rung removes text with no record and no size count, and no `depth_reduced` kind exists on the
wire (`r14`, `p13`) — R-DISC-028. *My evidence does not cover* the `format=raw` diff the Verify
clause names; that needs a live account.

**DISC-04 · Context efficiency against full dump · M**
**Recommendation: leave NOT TESTED, and do not quote any round's numbers — including round
25's.** `full_dump_tokens` is now charged through `row_tokens`, which is the right repair: the
dump and the disclosed side are finally in one unit, and the round-23 figures (0.216 / 0.881)
are correctly retired. I reproduce 0.101 / 0.846 on the round's own OD-3 fixture (`p24`). Those
numbers are honest arithmetic in the module's units, and **the units are invalidated for any
comparison with a host budget by R-DISC-032**, which is a stronger statement than round 23 could
make: it is not only that the estimate differs from the wire by a constant, it is that it is not
an upper bound at all.

**DISC-05 · Disclosure depth is justified by measurement · C**
**Recommendation: leave NOT TESTED, and raise the trigger question with the orchestrator again —
it has got worse, not better.** The level ships (WS-15 serves `segment`), the criterion requires
the comparison to exist before it does, and the comparison does not exist. Round 25 additionally
establishes that the shipped argument is **inert** (R-MCP-012, reproduced by me): twelve calls
with `segment` absent, `0` and `1` return the identical whole map. So a second navigational level
is published, unmeasured, and non-functional. *My evidence covers* that the boundary is derived
rather than invented and now derives from a per-row charge that reflects the wire; it covers
nothing about a measured win.

**DISC-06 · Self-truncation before host truncation · M**
**Recommendation: leave NOT TESTED. This remains the criterion I would most strongly resist any
future pass on, and I would now resist it more strongly than my predecessor did.** *Established
and earned:* the ladder's estimate and the envelope's estimate are one number on the shipped path
(delta 0 on five shapes, `p19`); `Envelope` refuses a payload over its declared ceiling and a
truncation claim with no artifact; a degradation step can no longer enlarge the response
(R-DISC-019, fixed); and the ladder's failure mode is a declared in-band refusal with an
executable retry rather than an unhandled exception (R-DISC-020, fixed). Those are four real
repairs. *False on execution:* the enforced quantity is not an upper bound on the rendered wire
in its own unit (R-DISC-032), and the rendered `CallToolResult` crosses the host's cap at twelve
messages while declaring itself complete and untruncated (R-DISC-033). DISC-06's acceptance says
host truncations are `0 [DEFINITIONAL]`; today the mechanism that would make that true does not
exist in the codebase in the unit the host uses.

**PART-05 · Unexpanded content is visible as stubs · M**
**Recommendation: leave NOT TESTED, and record the partial repair.** *Established:* stub rows and
collapsed runs are both charged, positions are bounded by `stated_total`, runs are contiguous and
counted, `included` counts run members, and a run's affordance is a call
`mailweave_thread_map` actually accepts (`r15` C: `{"tool": "mailweave_thread_map", "args":
{"thread_id": …}}`). A 400-row map now measures 3,515 tokens against 9,000, where round 23
measured a 600-row map at 8,300 and 702,915 characters. *Not established:* the guard. The map no
longer dominates the token budget and still renders over the host's cap (26,793 chars at 400
rows, 92,520 with 400 senders), so the thing the guard rules out is ruled out in the measured
unit and not in the binding one.

**EV-03 · Withheld-record discipline · M**
**Recommendation: leave NOT TESTED, and record it as the strongest thing in the disclosure
domain.** *Established by execution, four ways:* `accounted_ids` covers every mapped member on
the shipped path; steps 7 and 8 both file records with executable affordances and both are now
*charged* for doing so; the ledger derives the withheld set and `Envelope` refuses a disagreeing
list; `Source` forces three dispositions per position (`p05`, `p06`, `p18`, `p18b`, `p22`
re-run — 0 A.9(2) holes at every band size from 400 to 1,000 messages per thread). Nothing is
labelled withheld that is disclosed. *The one thing that would falsify it is not its own
defect:* when the host truncates a response MailWeave declared complete (R-DISC-033), evidence
is lost with no record — because the record was written and the reader never received it.

---

## An explicit ruling on the host-truncation issue

The orchestrator asked me to judge, under OD-7, whether the host-truncation issue prevents safe
and truthful end-to-end use, to measure it against realistic thread sizes, to say where the line
is, and to say whether it must be fixed before the live demo.

**Where the line is: twelve messages.** Not sixty. `r15_mcp_wire.py` measures the actual
`CallToolResult` — `structured_content` serialised plus the text content beside it, which is what
`anthropic/maxResultSizeChars` counts — and a twelve-message thread of ~110-word messages renders
25,358 characters against the [VERIFIED] 25,000-character cap. Fifteen messages is 1.15×; twenty
is 1.39×; forty is 2.31×. The 10,000-character warning is crossed at **five** messages. The
implementer's 60-message / 68,363-character figure is correct for their fixture and is not the
threshold; their fixture uses six-token bodies, and real messages are longer.

**It prevents safe and truthful end-to-end use, and it must be fixed before the demo.** Three
reasons, in order of weight:

1. **The response asserts a falsehood about itself at the moment it fails.** The 25,358-character
   response carries `truncated_by: null`, `partial: false`, `withheld: []`,
   `included: 12 of stated_total 12`, and `ceiling: {applied: 9000, why: null}`. The host then
   cuts it. The model is handed an incomplete thread that states it is complete, with no marker
   and no withheld record. That is the exact shape of the Gmail-connector defect this project
   was built to catch — a thread returned with the causing message missing and no truncation
   marker — reproduced by MailWeave, on an ordinary conversation, at shipped defaults. Under
   OD-7's line, "loses evidence without a withheld record" is the paradigm case.
2. **It is what the demonstration will hit.** OD-7 point 3 mandates demonstrating Claude
   retrieving real mail, and point 4 a comparison against the native connector on "ordinary cases
   and difficult conversations". Difficult conversations are long ones. Every difficult
   conversation in that comparison will be host-truncated while claiming otherwise, and the
   owner would be comparing MailWeave's evidence against the native connector's using evidence
   that was silently cut. An "early decision-making exercise" run on that basis produces a
   decision about a thing that was not measured.
3. **The mechanism that would catch it does not exist.** `grep -rl maxResultSizeChars
   server/src` returns nothing. There is no character-unit measure anywhere in the system, so
   this cannot be detected today by any test, gate or assertion. It is not a tuning error; it is
   a missing check.

**What is PF-6's and what is not.** I agree with the implementer that the *figures* 9,000 and
12,000 are `[DESIGN, set by PF-6]` and that re-deriving them in the host's unit is PF-6's work,
not this round's. I disagree that the whole issue is therefore PF-6's. Two parts are not:

* **R-DISC-032** — the estimate is not an upper bound on the rendered wire in **its own token
  unit**, because `participants` is uncharged. That is a defect in the measure, not in the
  figure, and PF-6 cannot be conducted meaningfully until it is fixed: any character bound
  derived against a token estimate that can be 2.6× low on an ordinary mailing-list thread would
  be derived against nothing.
* **The completeness assertion.** Whatever the ceiling figure turns out to be, a response that is
  over it must not say `truncated_by: null, partial: false, included: N of N`. Declining in band
  — which `DisclosureLadderExhausted` already does correctly, with a code, a reason and an
  executable retry — is a behaviour this codebase already has and already renders properly. The
  minimum fix before the demo is to measure the rendered form in characters in `call`, and, when
  it is over a published host-cap constant, either re-run the ladder at a lowered ceiling and
  declare the reduction, or decline the way the ladder already declines. That is a
  bounded change in one function plus one constant, and it is the difference between a demo that
  is honest about its limits and a demo that is silently wrong about a twelve-message thread.

**What I do not recommend:** raising the token ceiling, or lowering it by guesswork. Both are
PF-6's, both need R-DISC-032 fixed first, and neither addresses the false completeness claim,
which is the part that makes this a truthfulness defect rather than a size one.

---

## Overall verdict: is the thesis now a thesis?

**Half of it is, and the half that is, is genuinely new.**

Round 23 found a policy that was Baseline F under a query-aware name: six queries, one
representation, and an E4 top class that was the ±2 window position for position. Two of those
three sentences are now false, and they are false for principled reasons rather than for fitted
ones:

* **The ordering half is fixed and it is not fitted.** The key is the anchored score and the
  thread position; `POSITION_ADJACENCY` and `DECISION_CUE` are out of it; and at **no prefix**
  does the E4 top-k set equal Baseline F's top-k set, on either thread shape, for any of six
  queries. I attacked this at every prefix rather than at one, and it held. R-DISC-018 is closed.
* **A11's admission rule is implemented as stated and it generalises.** It is computed over
  facts, not written against the subject: a participant on every message and a date window the
  whole thread sits inside are held back exactly as the subject is, and admit exactly the
  messages that vary. I built the two threads the implementer said they had not built, and the
  rule handled both. This is the principled route R-DISC-017 offered, and it was taken.
* **Where the query's purchase is on each message's own text, the policy is genuinely
  query-aware end to end** — 10 of 10 pairs differ on my own thread, my own vocabulary and my own
  queries, for a reason a stranger can read off the reason strings.

**And then the rule meets the two characters Gmail puts in front of every reply.** `content_tokens`
keeps `re` as a content token, so a thread's root and its replies have different subject token
sets, so `message_discriminating_facts` classifies the subject — the archetypal thread-level
fact, the one A11 was written about — as message-discriminating. Where the root is a candidate the
fill collapses to zero; where the root is a hit the hit ranking goes uniform and reverts to
oldest-K. Driven end to end on the thread Gmail actually sends, five materially different queries
still produce **0 of 10** differing included sets and **0 of 10** differing depth maps, and the
protected hits are still the ten earliest by position. DISC-01's acceptance still fails on the
modal case.

The module's own docstring asserts the opposite of what it does — *"two messages whose subjects
differ only in a `Re:` prefix carry the same subject as the components read it"* — and the
fixture carrying the round's DISC-01 evidence names the prefix in prose and omits it from the
data. That is not tuning against a reviewer's probe set; the implementer was scrupulous about
that and I found no evidence of it anywhere. It is the narrower and more ordinary failure the
implementer themselves warned about in their last line: *"the rule is computed over the fact and
names no field, which makes it explainable; explainable is not correct."* They were right, and
the counterexample was two characters away.

**So: the thesis is a thesis on the shape the tests use, and not yet on the shape Gmail sends.**
The fix is small — the subject fact should be compared in the form the components claim to
compare it in, and `hit_ranks` should carry the same sweep `rank` carries — and after it the
ordering work, the `hit_ranks` placement, the floor oracle and the monotone ladder are all
genuinely load-bearing.

**On the round as a whole.** Parts 1, 3 and 4 each contain real, verified work: A11's rule
generalises, the ladder is monotone in cost, `DisclosureLadderExhausted` is a declared refusal,
the floor records hit-members, `floor_pairs` makes the gate relative, `hit_ranks` sits outside the
`Selector`, and the floor's oracle is hand-written and **disagreed with the implementation when I
planted the old defect back**. The second sitting's audit was the right method and it caught two
findings a diff-reader would have marked done; I applied the same method and it caught two more.
The report's "what I could not establish" sections are honest and, where I could check them,
accurate — with one exception that matters: Part 3 states the estimate/wire relationship as
established, and it is not established, because the field that dominates the wire is not charged
and the test that certifies it holds that field constant.

**I do not recommend declaring OD-6's milestone**, and I agree with the implementer that this
round did not advance it. Under OD-7 I recommend **three fixes before the live demonstration** —
R-DISC-031 with R-DISC-034, and R-DISC-032 with R-DISC-033 — and that everything else stay
tracked. R-DISC-033 is the one the owner named, and it is the one I would refuse to demo without.

---

## Established by execution

1. All gates clean on the current tree and reproducing the implementer's figures exactly: ruff,
   ruff format (198 files), `mypy --strict` (171 files), seven guards, `pytest -q -m "not
   network"` **EXIT=0** over **2,691** tests counted two independent ways with no F/E/s,
   `tests/test_replants.py` 4 passed over a **114**-entry manifest, rubric unchanged at
   6/0/0/107. `diff -rq` confirms I changed nothing.
2. **A11's admission rule generalises.** A participant on every message and a date window the
   thread sits inside are held back exactly as the subject is, and admit exactly the messages
   that vary (`r01`). It is computed over `CANDIDATE_FACTS` and names no field.
3. **The ordering half is fixed at every prefix.** For six queries on two thread shapes, no
   prefix k ≥ 2 has the E4 top-k set equal to Baseline F's top-k set (`r13`). R-DISC-018 closed.
4. **A degradation step can no longer make the response larger.** A stub costs 120 and a snippet
   180; step 1 takes 56,300 → 37,880 where round 23 took 9,300 → 27,270 (`p08` re-run, `r10` C).
   R-DISC-019 closed.
5. **`DisclosureLadderExhausted` reaches a client as a declared in-band refusal** with `code`,
   `declined: budget_exhausted`, `remediation` and `retry_with` (`r15` B). R-DISC-020 closed.
6. **The floor records hit-members, and its oracle is real.** Planting round 23's skip back into
   an isolation-asserted whole-tree copy turned three tests red, and the hand-written
   `ORACLE_FLOOR` failed *as an oracle*, naming `h-003` and `h-004` — the two hits that are each
   other's parent and child. The driver gate caught the second case independently. R-DISC-021
   closed.
7. **`hit_ranks` is real at the planner and is computed outside the `Selector`.** Scores match a
   hand-typed oracle (`004 012 020 028`), both arms agree, and the only call site is in
   `plan_thread` outside `selector.select` (`r04` C/D).
8. **`layout.cost() == measure_tokens(envelope)` survives**, delta 0 on five shipped-path shapes
   from 5 to 600 messages (`p19` re-run), and the estimate is inside the applied ceiling at seven
   sizes up to 700 messages (`r14`).
9. **The single `Selector` survives**: `def select(self` is defined in exactly one file, and
   `FixedWindow().radius` is still `E4_ADJACENCY_POSITIONS`.
10. **EV-03's record discipline survives four attacks** (`p05`, `p06`, `p18`, `p22` re-run): 0
    A.9(2) holes among disclosed hits at every band size, records filed with executable
    affordances, the withheld set derived by the ledger, three dispositions forced per position.
11. **Where the query's terms live in each message's own text, disclosure is query-aware end to
    end**: 10 of 10 pairs differ across five queries on one thread (`r03` B).

## False on execution

1. **"Two messages whose subjects differ only in a `Re:` prefix carry the same subject as the
   components read it"** (`weights.fact_values`). `content_tokens` keeps `re`; the token sets
   differ by exactly `{re}`; `subject` is classified message-discriminating on the shape Gmail
   sends (`r06`). — R-DISC-031
2. **"Six materially different queries over one thread produce 15 of 15 differing fills"** as a
   statement about the modal Gmail case. End to end on the thread Gmail actually sends, five
   queries produce **0 of 10** differing included sets and **0 of 10** differing depth maps
   (`r04` A). The 15/15 is true of a fixture whose subjects omit the prefix its own docstring
   names. — R-DISC-031
3. **"Which hits are the top k is decided by the published E4 score … deliberately not by
   recency and not by arrival order"** (`DISCLOSURE_TOP_K_HITS`). On Gmail's shape every hit
   scores the same nonzero value and the protected set is the k earliest by position, in both
   arms, for every query (`r04` B, `r06` D). R-DISC-026 is fixed where hits differ in their own
   text and not otherwise. — R-DISC-034
4. **"The estimate the ceiling is enforced against is an upper bound on the rendered response,
   in the same whitespace-token unit."** False at 50 distinct senders on a 400-message thread
   (ratio 1.083) and at 25 there is no margin (0.976); worst measured 11.46×. `participants` is
   82 % of the rendered response and is charged nothing (`r11`, `r12`). — R-DISC-032
5. **"A response never exceeds the ceiling it declares"**, in the unit the host enforces. A
   twelve-message thread renders a 25,358-character `CallToolResult` against a 25,000-character
   cap while declaring `truncated_by: null`, `partial: false`, `withheld: []`,
   `included: 12 of 12` and `ceiling.applied: 9000, why: null` (`r15`). — R-DISC-033
6. **"A11's rule is monotone in what the query reached."** Making one more message match removes
   nine other matching messages from the disclosure (k=19 → k=20: |fill| 9 → 0, |included| 20 →
   11), and "no message relates" and "every message relates" render identically (`r02`, `r09` C).
   — R-DISC-035
7. **"`test_the_estimate_is_an_upper_bound_on_the_rendered_wire` measures the shape matrix."** It
   is parametrised over six *sizes* of one shape whose participant list is two entries at every
   size (`_long_thread`). — R-DISC-036
8. **"Silent reductions: 0"** (DISC-03). Unchanged from round 23: no reduction record and no
   `depth_reduced` kind on the wire at a binding ceiling (`r14`, `p13`). — R-DISC-028
9. **"The promotion rule discriminates."** A one-word `thanks` parent and a parent with no
   observed text at all are both promoted; `constraint_carrier` fires on no input this system
   produces (`p09`, `p10` re-run). — R-DISC-024
10. **"Promotion earns a depth."** `FLOOR_PROMOTED_DEPTH` is `body_clean` but is reachable only
    where a body was fetched, and disclosure never fetches; promoted and unpromoted floor members
    carry the same depth (`r14`, `p11` re-run). — R-DISC-025
11. **"A.8a's decision lexicon catches the reversal A.9a's honesty note quotes."** Eight of ten
    ordinary reversals are refused, including *"Actually, let's not — we're pushing to Q4"*, which
    is the sentence A.9a quotes (`p20` re-run). PF-13's, unchanged.
12. **"`segment` is a shipped navigational level."** Twelve calls with it absent, `0` and `1`
    return the identical whole map (`p21`, `r14`). — R-MCP-012

## Not establishable here at all

1. **DISC-02's comparison, DISC-04's bars, DISC-05's depth arm, and F17 at each tier.** Each
   needs the WS-16 harness and G0-registered numbers. I confirmed the hooks exist and the arms
   are runnable; I did not run them and no in-process test can. OD-7 explicitly does not build
   WS-16 for the checkpoint comparison.
2. **Whether the E4 order is *better* than the baseline's.** It is a mechanical sum of five
   predicates with no measured relation to relevance. The implementer says so and is right.
3. **The pinned tokenizer, and therefore every token figure in this review.** PF-6. What I *can*
   establish is a statement about the estimate rather than about the number: it is not an upper
   bound on the wire even in its own unit (R-DISC-032), which is a defect PF-6 cannot repair.
4. **The right value for the host character cap on the owner's actual client.** I take the
   [VERIFIED] 25,000 / 10,000 from AD PF-6 as given. If the real cap is higher, R-DISC-033's
   threshold moves and its two structural halves — the missing character measure and the false
   completeness claim — do not.
5. **Whether A.8a's decision lexicon has a usable base rate on real mail.** PF-13. If it is inert
   the `CONTRADICTION` clause is inert with it.
6. **Whether one day is the right `E4_TEMPORAL_PROXIMITY_SECONDS`.** Derived from Gmail's
   day-granular date operators, which is an argument and not a measurement. WS-16/WS-17.
7. **The real-mail rate at which a reversal falls past Gmail's ~200-character snippet.** The
   mechanism reproduces (`p11`); I have no corpus that would settle the rate and OD-4 forbids me
   one.
8. **Whether real Gmail localises the reply prefix.** R-DISC-031's mechanism is the `Re:` token;
   whether a mailbox in another locale sends `Antw:`, `Sv:` or `回复:` — and therefore whether the
   fix must strip a family rather than one string — needs a real account. The fix should be
   written against a family for the same reason OD-5 point 3 required the scope-operator rule to
   be derived rather than listed.
9. **Anything requiring a live account** — OD-6 criteria 2, 3 and 4-on-real-mail. OAuth consent
   status is unchanged and untouched by round 25.
