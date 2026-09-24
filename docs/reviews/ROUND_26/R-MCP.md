# ROUND 26 — R-MCP, the gating review

**Reviewer:** R-MCP · **Date:** 2026-09-06 · **Scope:** the eight findings
`docs/reviews/ROUND_26/WORK_ORDER.md` names, under **OD-7**.
**One question:** is the surface now safe and truthful enough for a live demonstration of
Claude retrieving real mail?

**I did not write this code and I have not taken the implementer's report as evidence.** Every
number below is off an object a real MCP `Client` received over the shipped `Server.run` loop, or
off a direct `call` where the point is a producer the client cannot reach. Where I could not
establish something I say so at the end.

---

## Environment

Working tree `/root/mailweave` (not a git repository; nothing in it was modified). My scratch
copy is `/tmp/rmcp26/tree` — the **whole** tree including `docs/` — with all three packages
asserted resolving inside it before any probe runs:

```
$ /root/mailweave/.venv/bin/python /tmp/rmcp26/env.py
mailweave            /tmp/rmcp26/tree/server/src/mailweave/__init__.py
mailweave_harness    /tmp/rmcp26/tree/harness/src/mailweave_harness/__init__.py
tools                /tmp/rmcp26/tree/tools/__init__.py
docs/ present; three packages resolve inside /tmp/rmcp26/tree
```

`PYTHONPATH` is explicit in `/tmp/rmcp26/kit26.py` (`TREE`, `TREE/server/src`,
`TREE/harness/src`) and re-asserted at import. Replants are applied **to the scratch copy only**
(`/tmp/rmcp26/plant.sh`), and the four files I planted into were diffed back against the working
tree afterwards and are byte-identical.

My probes are `/tmp/rmcp26/p1..p19_*.py`. My vocabulary is invented (`glimmerwrack`, `tannoy
sluice`, `zorrick`, `plimwattle`, `marklewisp`, …), addresses are `.example`/`.invalid` only
(RFC 2606/6761), and no fixture contains real or realistic personal mail. My thread shapes are
mine: they parameterise the five dimensions the work order names — body length, message count,
distinct-sender count, recipient-list length, attachment presence and quoting depth — plus
multi-thread search results, which turned out to be the dimension that matters.

**Round-25 reproduction scripts.** `/tmp/rmcp25/{p3_filename,p4_token,p6_hostcap}.py` and
`/tmp/rdisc25/{r04,r06,r08,r12,r15}*.py` are present and were re-run unmodified. `/tmp/rmcp25/kit.py`
puts `/root/mailweave` on the path, so those run against the live tree. `/tmp/rdisc25/renv.py`
points at `/tmp/rd25`, which I diffed against the working tree first: `server/src` differs in one
docstring in `disclosure/layout.py` and `tests/` in one docstring in `test_round26.py`, both
comment-only. Noted rather than assumed, and the difference is itself evidence — see §2.4.

---

## Priority 1 — the host cap, from the client's side

### 1.1 What I measured, and where

`kit26.client_chars(result)` is `len(json.dumps(result.structured_content)) + len(text mirror)`,
computed on the `CallToolResult` object the SDK client handed back. That is
`envelope.measure.rendered_chars`' own definition applied to the client's copy, and it is not read
from anything the server computed.

### 1.2 The sweep (`/tmp/rmcp26/p1_hostcap.py`, `p2_search_decline.py`)

`mailweave_thread_map` returns stub rows and carries no body text, so body length, attachment
presence, quoting depth and subject length change its size **not at all** (5 messages of 110 words
and 5 of 20,000 words both render 6,998 characters). The body-bearing paths are `mailweave_search`
and `mailweave_get_messages`; those are where the cap is decided. On one thread of ~110-word
messages, through the client:

| messages | rendered chars | truncated_by | partial |
|---|---|---|---|
| 1 | 6,436 | null | false |
| 3 | 11,908 | null | false |
| 5 | 17,380 | null | false |
| 7 | 22,858 | null | false |
| **8** | **24,081** | **mailweave** | **true** |
| 12 | 23,644 | mailweave | true |
| 30 | 18,047 | mailweave | true |
| 60 | 18,347 | mailweave | true |

Seven at full body depth, degrading from eight — the range the implementer reports, on my fixture,
which is a different fixture. `/tmp/rmcp25/p6_hostcap.py` re-run agrees (every size 3→40 inside the
cap, worst 23,467 at n=8 = 0.94×; was 27,957 at n=7 and 70,682 at n=40).
`/tmp/rdisc25/r15_mcp_wire.py` re-run agrees (12 messages: 23,990, was 25,358).

**I could not find a served response that crosses 25,000 characters without `truncated_by` saying
so.** Not on long single messages, not on many short ones, not at 400 distinct senders with
25-recipient lists and 310-character addresses, not on a thread of attachments, not at quoting
depth 40, not on 400-character subjects, not on any of the four tools. That is the exit condition
and it holds.

### 1.3 But the thing that stops it crossing is a **backstop**, not the ladder

`/tmp/rmcp26/p3_estimate.py` raises the constant `surface/partition.declared_result` compares
against, leaving `SERVED_CEILINGS.host_chars` at 25,000, so what the **ladder alone** would serve
is rendered and measured. `/tmp/rmcp26/p3b_gap.py` then captures the winning layout's own
`layout.chars()` by wrapping `run_ladder` at the two names that hold it (`disclosure.plan`,
`surface.expansion`):

| shape | sources | `layout_chars` (estimate) | `rendered_chars` (wire) | slack |
|---|---|---|---|---|
| search, 1 thread × 8 | 1 | 24,350 | 24,081 | **+269** |
| search, 1 thread × 60 | 1 | 19,768 | 18,347 | +1,421 |
| thread_map, 12 | 1 | 14,994 | 12,868 | +2,126 |
| get_messages, 12 body_full | 1 | 18,868 | 17,654 | +1,214 |
| **search, 2 threads × 3, 90 words** | **2** | **20,292** | **20,304** | **−12** |
| **search, 3 threads × 3, 90 words** | **3** | **24,813** | **25,081** | **−268** |
| **search, 4 threads × 3, 40 words** | **4** | **24,854** | **25,319** | **−465** |
| **search, 6 threads × 1, 90 words** | **6** | **24,812** | **26,314** | **−1,502** |
| **search, 12 threads × 1, 40 words** | **3** | **24,683** | **26,196** | **−1,513** |

The estimate is above the wire on every **one-source** response and below it on every
**multi-source** one. The implementer's report says, of this exact number: *"worst slack **+530
characters**, ratios **1.03 to 1.68** over seventeen shapes across all three tools … **Never
negative — which is the direction that matters**."* That sentence is **false on execution**. The
worst slack I measured is **−1,513**, and the sign flips as soon as a search returns more than one
thread. `disclosure/layout.py::layout_chars`' own docstring states the property as a requirement —
*"this number must be at or above the rendered one"* — and it does not hold.

The reason it survived is in the test: `test_the_character_estimate_bounds_the_rendered_result`
runs ten shapes that vary message count, body length, sender count and recipient-list length, and
every one of them is **`_thread_mailbox`, one thread, thread id `h-th`**. Source count is the one
dimension held constant, and it is the one the estimate fails on. The test also holds the
*consequence* (`assert real <= HOST_RESULT_CHAR_CAP`) with `if result.is_error: continue`, so a
response that declines instead of serving passes it silently. This is the same shape R-DISC-036
filed against round 25's token matrix, one round later, in the other unit.

### 1.4 What the under-charge costs: ordinary searches now return nothing

Because the estimate under-charges, the ladder hands `declared_result` a response over the cap;
the surface measures it, raises `HostCapExceeded`, and `call` turns that into a declined
`budget_exhausted` result. So an **ordinary multi-thread search declines entirely**
(`/tmp/rmcp26/p2_search_decline.py`, at the client):

```
threads=3 per=3 words=90   DECLINED budget_exhausted  (renders 25,081)
threads=4 per=3 words=40   DECLINED budget_exhausted  (renders 25,319)
threads=6 per=1 words=90   DECLINED budget_exhausted  (renders 26,314)
threads=12 per=1 words=40  DECLINED budget_exhausted  (renders 26,196)
threads=30 per=1 words=10  DECLINED budget_exhausted
```

Thirty one-message threads of ten words each — a search result a person would call small — comes
back with no mail in it. My message ids are nine characters (`M-000-000`) and my addresses are
short; a real Gmail id is longer and a real body is longer, so on the owner's mailbox the
threshold is **lower**, not higher.

This is honest — the response says it declined, says the measured size, and names the disagreement
between the estimate and the render. It is not a truth defect. It is a capability defect on the
modal demo query, and it is caused by the round's own fix.

### 1.5 The way out of the decline is not executable

`surface/server.py::_narrower_call` mints, for `mailweave_search`:

```json
{"tool": "mailweave_search", "args": {"query": "…", "budget": {"max_hit_threads": 1}}}
```

`surface/arguments.py::BUDGET_KEYS` does not contain `max_hit_threads`. Executing the affordance
the server just handed back gives, through a real client (`/tmp/rmcp26/p5_affordance.py`):

```
hop0: declined budget_exhausted -> retry_with={"tool":"mailweave_search",
       "args":{"query":"glimmerwrack","budget":{"max_hit_threads":1}}}
hop1: JSON-RPC -32602  mailweave_search: unknown budget key 'max_hit_threads';
       this tool accepts ('max_quota_units','max_ms','max_disclosed_tokens','max_api_calls',
       'max_http_requests','max_server_ms','max_semantic_ms')
```

Both producers reach it — the new `HostCapExceeded` clause and the older
`DisclosureLadderExhausted` clause pass the same `_narrower_call`. `_narrower_call`'s own docstring
says *"a refusal offering a call that would fail again is worse than one offering nothing."*
Executed, that is what it does. **PRODUCT_CONTRACT I-2 proof-of-violation (c)** is exactly *"an
affordance that errors … or is not executable by an ordinary MCP client"*.

The `thread_map` half of `_narrower_call` mints `{"segment": 0}`, and `segment` is still inert
(§6.1), so that retry is a no-op rather than an error. No test in the suite executes either minted
call.

### 1.6 When MailWeave does cut, what does it leave?

On a single thread the cut rows are **not** lost: at n=8..12 every message is still a row at a
reduced depth; at n=20..60 five rows survive and the rest become one **declared collapsed run**
carrying every member id and an expansion affordance (`collapsed positions 5-23: 19 messages not
shown, expand with mailweave_thread_map`), with `included 24 of stated_total 24, as_stub 19`. On a
multi-thread search that survives, step 7/8 produce real `withheld` records and
`not_included_sources` entries whose `why` names the cap in terms:

```
withheld why: A.9a: the response did not fit the host's 25000-character result cap. The published
              token ceiling does not bound the rendered response in characters, so A.9a re…
```

That half is good. Two gaps sit beside it:

* **`ceiling.why` is `null` on every host-capped response I produced**, including ones where the
  layout's own `host_capped` flag is `True` and `truncated_by` is `mailweave`. The reader sees
  `ceiling: {normal: 9000, applied: 9000, why: null}` and is left to conclude the token ceiling
  bound. `HOST_CAP_WHY` is only ever written onto withheld records and `not_included_sources`
  entries — and the **common** reduction (depth demotion, collapsed run) produces neither. The
  hazard is named in `retrieval/assemble.py:1541`'s own docstring and then closed on one path only.
* A row demoted from `body_clean` to `snippet` carries `reductions: []` — no record of the
  demotion (R-DISC-028, tracked; confirmed still live, §6.2).

---

## Priority 2 — the `Re:` prefix and A11

### 2.1 What the 17-marker set takes (`/tmp/rmcp26/p6_prefix.py`)

`strip_reply_prefixes` takes `Re:`, `RE:`, `re:`, `Re:` with no space, `Re : ` with a space before
the colon, `Re[2]:`, `Re(3):`, `Fwd:`, `Fw:`, `AW:`, `SV:` and stacked `Re: Fwd: Re:` — all to the
bare root subject. It leaves `budget: q3` alone. That is Gmail's own English behaviour and
fourteen localised markers, and it is correct.

It does **not** take: `[EXTERNAL]`, `[EXT]`, `**EXTERNAL**`, `[SPAM]` (corporate gateway tags);
`VB:` (Swedish Outlook forward), `VL:` (Finnish forward), `R:` / `I:` (Italian Outlook),
`Yan:` / `YNT:` / `ILT:` (Turkish), `Odg:` (Croatian), `Vá:` (Hungarian), `ΑΠ:` / `ΣΧΕΤ:` (Greek);
`Automatic reply:`.

### 2.2 Does that matter? Only when the decoration is **asymmetric** (`/tmp/rmcp26/p8_a11.py`)

My own 24-message fixture: one subject carrying all five query terms, so `TERM_OVERLAP` fires from
the subject on every candidate and A11's narrowing is the only thing that can stop the subject
deciding; each candidate's own snippet carries one of the five terms, so the snippets are what must
decide instead. Hits at positions 1, 9, 17 — a placement where the root is a **candidate**.

| subject convention | discriminating facts over the candidate pool | differing fills |
|---|---|---|
| flat (round 25's fixture) | text, positions, seconds | **10/10** |
| **`S` / `Re: S` (Gmail's own)** | text, positions, seconds | **10/10** |
| `S` / `AW:` mixed with `Re:` | text, positions, seconds | **10/10** |
| `[EXTERNAL] S` inbound only, `Re: S` outbound | text, positions, seconds, **subject** | **0/10**, \|fill\| = 0 |
| `VB:` from one participant, `Re:` from others | text, positions, seconds, **subject** | **0/10**, \|fill\| = 0 |
| `[EXTERNAL] S` → `Re: [EXTERNAL] S` (uniform) | text, positions, seconds | **10/10** |
| `[glimmer-dev] S` mailing-list tag (uniform) | text, positions, seconds | **10/10** |
| **a genuinely changed subject mid-thread** | text, positions, seconds, **subject** | **10/10**, \|fill\| 7–8 |

Three things this establishes:

1. **R-DISC-031 is closed for the shape Gmail sends.** `Re:` behaves exactly as the flat fixture.
2. **The repair is a repair and not a removal.** A subject that genuinely changes mid-thread is
   still message-discriminating **and** still produces ten differing fills — so the fact is not
   being thrown away, it is being compared correctly.
3. **The defect returns in full on asymmetric decoration outside the marker set.** `[EXTERNAL]`
   applied to inbound only, or one participant's client writing `VB:` while others write `Re:`,
   restores exactly R-DISC-031: `subject` becomes discriminating and the fill collapses to **zero**
   for every query. Uniform decoration is benign, which narrows the residual considerably.

### 2.3 `hit_ranks` (R-DISC-034)

On a 12-hit pool the sweep is present in both callers: `flat`, `gmail`, `aw` and `changed` all give
distinct anchored values `[0, 4]` — the query separates hits — and the two broken conventions give
`[0]`, a **stated zero**, so position decides for a stated reason rather than a uniform nonzero
masquerading as a score. `a11_scores` is one function and `rank` and `plan.hit_ranks` both read it.
R-DISC-034 is closed as scoped.

### 2.4 The docstring that was softened

`/tmp/rd25/server/src/mailweave/disclosure/layout.py` (the implementer's own copy, taken mid-round)
says the character estimate *"is above the rendered one on every shape the matrix covers"*. The
shipped file says *"must be at or above … held by consequence rather than by comparison"*. The
claim was weakened in the source and left unweakened in the report. See §1.3.

---

## Priority 3 — the filename and the fence sweep

### 3.1 The attack is closed (`/tmp/rmcp25/p3_filename.py`, unmodified)

Control (`invoice.pdf`): `isError=False`, one fenced block, **0 disagreements, 0 forged lines**.
The attack (`\n` plus four connector-voiced lines in the filename): the response model refuses and
the call comes back as `-32603`. No forged `withheld` record, no forged source, no re-attributed
body, on any tool.

### 3.2 Blast radius (`/tmp/rmcp26/p9_fence.py`, `p11_blast.py`)

Confined to `mailweave_get_attachment`. `search`, `thread_map` and `get_messages` never populate
`attachments`, so a message with a hostile filename does not poison the queries that touch its
thread. That is the right containment and it is worth recording.

### 3.3 Is the sweep's list complete? (`/tmp/rmcp26/p12_sweep.py`)

I enumerated every `str`-bearing field of every wire model, then drove sender-chosen values through
the shipped surface looking for the marker in the residue or in `structuredContent`. **None of
these reached the wire**: `From` display name, `To`/`Cc` display names (3 recipients), `Reply-To`,
`List-Id`, `Message-ID`, `In-Reply-To`, `References`, `Subject`, the Gmail `snippet`, and
`Content-Type; name=`. `marker-in-structured=False`, `marker-lines-in-mirror=0`,
`disagreements()=0`, on all three tools, every case. The report's two structural claims hold: there
is no subject field on any wire model, and there is no `display_name`.

**One family the table does not name.** `Reduction` is a `SealedModel` on the wire with seven free
`str | None` fields — `detail`, `mime`, `parser`, `stripper`, `charset_used`, `charset_declared`,
`header` — and none of them carries `is_one_line` or a length bound. `charset_declared` and `mime`
are read straight off the sender's `Content-Type`; `header` is a header name the sender wrote. They
are **not** in the sweep table, which accounts for `*.why`, `*.note`, `*.scope`, `Score.*`,
`Shortlist.rule`, `PoolBlock.*`, `Source.source` and `Counters.quota_units_label` as "strings this
server wrote" and does not mention `Reduction` at all. Today the text mirror renders only a
reduction's `kind` and `removed_chars`, so a line break in one of them cannot close the fence — but
the renderer invariant `_every_line_is_one_record` protects only values the mirror interpolates,
and these reach `structuredContent` unbounded. This is the "field nobody has written yet" the
structural half was meant to cover, already present.

### 3.4 What the new bound costs on ordinary mail

`SenderScalar` refuses, and the refusal is a `-32603` "this is a defect in this server". Two
triggers that are not attacks (`/tmp/rmcp26/p10_why.py`):

* **An empty filename.** `is_one_line("")` is `False` (`"".splitlines() == []`), so
  `AttachmentMetadata(filename="")` raises. `content/mime.py:32` treats a part as an attachment if
  it has a filename **or** an `attachmentId`, so a part Gmail returns with `"filename": ""` and an
  attachment id — an inline image in an HTML signature, among others — reaches the model and is
  refused.
* **A filename over 255 characters.** 251+`.pdf` serves; 300 characters is refused.

The implementer's N-4 names only control characters. Length and emptiness are the ordinary-mail
triggers and they belong on the same finding.

---

## Priority 4 — the re-auth path

### 4.1 Both producers, all four tools (`/tmp/rmcp26/p16_auth.py`)

Eight cases, each driven through a real MCP client:

```
ConsentFailed (refresh refused)    search / thread_map / get_messages / get_attachment
    isError=True  code=auth_reauth_required  instruction present   OK ×4
TokenStoreError (store vanished)   search / thread_map / get_messages / get_attachment
    isError=True  code=auth_reauth_required  instruction present   OK ×4
```

`/tmp/rmcp25/p4_token.py` re-run unmodified — a real `StoredTokenProvider` on an injected clock
against a token endpoint answering `400 invalid_grant`, which is the mid-**request** producer the
`open_client` injection does not reach — gives the same, direct and through the SDK:

```
C. a refresh that FAILS mid-session, on a live tool call
   isError=True code=auth_reauth_required
   "…run `mailweave auth login` to re-authorise the read-only client (auth_reauth_required)."
D. the credential store becomes unreadable mid-session
   isError=True code=auth_reauth_required
   "no credentials at …; run `mailweave auth` to authorise the read-only client"
```

Both were `-32603 Internal server error` with empty `data`. **R-MCP-017 is closed on both clauses I
asked for**, and the implementer was right to refuse clause 2.

### 4.2 R-MCP-006's four-cause startup diagnosis still holds

`tests/test_round25.py::test_each_startup_credential_failure_reports_itself_as_itself` and
`tests/test_round26.py::test_the_startup_path_still_tells_the_four_credential_causes_apart` both
pass on the working tree. `gmail/client.py:450` records, at the line itself, why `access_token()`
is deliberately **not** wrapped. That is the right call and it is documented where the next person
will reach for it.

### 4.3 One false sentence left behind by the reverted half

`surface/server.py`, in the comment on the clause that was actually added:

> `GmailClient._request` **now wraps its own `access_token()` call**, so a refresh refused mid-call
> arrives as a `GmailAuthExpired` on the clause above. This clause covers the producers that are
> not inside a Gmail request at all …

`gmail/client.py:450` says the opposite in bold: *"`access_token()` is deliberately **NOT** wrapped
into a `GmailFault` here."* The clause the comment is attached to is in fact the **only** thing
catching the mid-call refusal, and the comment tells a reader it is not. Two sentences in one
round's change contradicting each other, on the path the round exists to protect.

---

## Priority 5 — N-1, ruled

**The measurement** (`/tmp/rmcp26/p17_n1.py`). A 24-message thread in which every message carries
every query term, so every message is a hit for every query. Five queries, at the client:

```
query=zorrick     rows=5  bodied=5  H-000..H-004
query=plimwattle  rows=5  bodied=5  H-000..H-004
query=grendaskew  rows=5  bodied=5  H-000..H-004
query=vurblesnit  rows=5  bodied=5  H-000..H-004
query=quandrelly  rows=5  bodied=5  H-000..H-004
distinct bodied sets across five queries: 1
```

Five materially different queries, one representation, and the messages that got depth are the
earliest by position. `retrieval/ladder.py::_fetch_bodies(run, sorted(run.evidence_ids), …)` is the
mechanism and no disclosure rule reaches it. R-DISC-031(b)'s end-to-end 0-of-10 is intact and the
A11 repair does not touch it. The implementer is right about this and right to have filed it.

**The ruling OD-7 asks for.** *Does the response say depth was allocated by position, or present it
as query-scored?* It does **neither**, and that is the answer:

* every bodied row's reason is `"gmail q matched at L1: zorrick"`, `reason_detail.kind =
  gmail_query_match` — a true statement about why the row is **in** the response, not a claim about
  why it got depth;
* `score` is `null` on every row, so there is no fabricated relevance number (C-04 (c) holds);
* the response declares `included 24 of stated_total 24, as_stub 19`, `truncated_by: mailweave`,
  `partial: true`, and a collapsed run naming all nineteen with an expansion call, so it does not
  claim the other messages did not match;
* **no tool description on this surface claims relevance-ranked depth.** I read all four
  descriptions for language about relevance, ranking, scores or "which messages": there is none.

So the response is silent about the depth rule rather than false about it. What is missing — a
record saying *why this row is at this depth* — is R-DISC-028, already tracked. **Under OD-7 this
is track, not fix.** Two conditions on that ruling, and they are not decoration:

1. **Nothing said about the demonstration may describe depth as query-aware.** If the OD-7 point-4
   comparison against the native connector concludes anything about the query-aware thesis, it will
   be concluding it from a run in which, on an all-hit thread, the thesis did not fire.
2. The moment a `Score` block or a "most relevant" sentence appears on this path, N-1 becomes a
   truthfulness defect. It is not one today because the surface makes no claim it cannot keep.

---

## Priority 6 — three tracked findings, spot-checked (`/tmp/rmcp26/p18_tracked.py`)

| tracked finding | my check | still true? | genuinely track-not-fix? |
|---|---|---|---|
| **R-MCP-012** — `segment` published and inert | 240- and 400-message threads, `segment` absent/0/1/2/99: identical rows, identical runs, identical `included` | **yes, inert** | **Yes as a capability** — the level ships and does nothing, which is a DISC-05 problem, not a safety one. **But** `_narrower_call` mints `segment: 0` as `thread_map`'s narrower retry, so the retry is a no-op. That consequence is new this round and is folded into R-MCP-025 |
| **R-DISC-028** — a depth demotion leaves no reduction record | 12-message search, histogram `body_clean 5 / snippet 1 / stub 6`; the demoted row carries `reductions: []` and `unabridged: true` | **yes** | **Yes.** The response-level declaration (`truncated_by: mailweave`, `partial: true`, `as_stub`, an affordance on every row) is present and true; what is missing is a per-row record. Nothing is asserted falsely |
| **R-MCP-019** — `sufficiency` / `not_included_sources` rendered, never read back | flipped `sufficiency` in a copy of `structuredContent` and re-ran `disagreements()`: **0** | **yes** | **Yes.** This is the strength of the parity check, not a defect a user meets. It should be fixed before MCP-03 is marked, and it does not touch the demonstration |

---

## Priority 7 — gates and replants

Re-run on the working tree, my own invocation (`/tmp/rmcp26/gates.sh`, `gates.log`):

```
ruff check .                 All checks passed!
ruff format --check .        199 files already formatted
mypy --strict server/src     Success: no issues found in 84 source files
python -m tools.guards       guards clean: forbidden-import, generative-client, gmail-endpoint,
                             ground-truth-isolation, scope-literal, unaudited-disk-write,
                             unwrapped-http-client over server/src
python -m tools.rubric_status  PASS 6 · FAIL 0 · BLOCKER 0 · NOT TESTED 107 (113 criteria)
pytest -q -m "not network"   2,737 collected, all pass. **exit status 0**, progress output
                             dots to 100 % with no F and no E. This pytest build emits no
                             "N passed" line (round 25's own artifact shows the same), so the
                             count is `--collect-only -q` summed per file - 2,737, matching
                             the figure the implementer reports - and the pass is the exit code
```

`FINDINGS_LEDGER.md` and `RUBRIC_TRANSITIONS.md` are untouched; no criterion is marked; ROUTE-01 is
not restored.

**Replants, my own way** (`/tmp/rmcp26/plant.sh` — applied to my scratch tree, never the working
tree; each anchor asserted to match exactly once; each named catcher run alone):

| plant | anchor matches | catcher |
|---|---|---|
| R115 the reply prefix is content again | 1 | both named tests FAILED |
| R117 the surface stops measuring the rendered result | 1 | named test FAILED |
| R120 a sender-chosen filename is unbounded again | 1 | both named tests FAILED |
| R122 a credential failure escapes the partition again | 1 | named test FAILED |

Four of eight spot-checked, chosen as the four closest to the demonstration. All four catch
individually. The scratch files were diffed back against the working tree afterwards and are
identical.

**One documentation defect from this round:** `docs/ARCHITECTURE_AMENDMENTS.md` now has **two**
sections numbered `### A12.3` (line 600, the new second-ceiling record, and line 644, A.9(2)'s
floor). An append-only document with a duplicated identifier cannot be cited unambiguously.

---

## Findings

Numbered from R-MCP-023. **Blocks-demo?** is the OD-7 question — *does this prevent safe or
truthful end-to-end use of the live demonstration* — and is separate from severity.

| # | finding | Severity | Reachability | **Blocks demo?** |
|---|---|---|---|---|
| **R-MCP-023** | An ordinary `multipart/alternative` message makes `mailweave_search` and `mailweave_get_messages` fail with `-32603` "a defect in this server". `MessageRow._reductions_have_an_unabridged_path` refuses any reduction with `removed_chars == 0` and no `count`, with **no exemption list**, while `Reduction._kind_specific_obligations` exempts exactly those kinds. Four ordinary-mail reductions are built that way | **HIGH** | REACHABLE-IF-GMAIL — near-certain on any real mailbox; the synthetic mailbox never emits `multipart/alternative`, so no end-to-end test has ever produced one | **YES** |
| **R-MCP-024** | `layout_chars` is **not** an upper bound on `rendered_chars`: under by up to **1,513** characters on every multi-source response. Consequence: ordinary multi-thread searches decline with no mail (3 threads × 3 messages; 30 one-message threads). The report's "never negative … worst slack +530" is false on execution | **HIGH** | REACHABLE today, shipped defaults, at the client. Real ids and bodies lower the threshold | **YES** (capability, not truth) |
| **R-MCP-025** | The narrower retry the surface offers is not executable. `_narrower_call` mints `budget: {max_hit_threads: 1}` for `mailweave_search`; `BUDGET_KEYS` does not accept it → `-32602`. Both producers (`HostCapExceeded`, `DisclosureLadderExhausted`) pass through it. The `thread_map` half mints an inert `segment: 0`. **I-2 proof-of-violation (c)** | **HIGH** | REACHABLE today — it is the only way out of R-MCP-024's decline | **YES** |
| **R-MCP-026** | `ceiling.why` is `null` on every host-capped response. `HOST_CAP_WHY` is written only onto `withheld` records and `not_included_sources` entries, and the **common** reduction (depth demotion, collapsed run) produces neither, so nothing in those responses names the cap that actually bound. A reader is sent to `max_disclosed_tokens`, which does nothing | MEDIUM (honesty) | REACHABLE today — every single-thread host-capped response | no — **track**, but it is a one-field fix and I would take it |
| **R-MCP-027** | The reply-prefix repair is closed for Gmail's own markers and open for **asymmetric** subject decoration outside the 17: `[EXTERNAL]`-style gateway tags applied to inbound only, and `VB:`/`VL:`/`R:`/`I:`/`YNT:`/`İLT:`/`Odg:`/`Vá:`/`ΑΠ:`/`ΣΧΕΤ:`. On those, `subject` is discriminating again and the fill collapses to **0/10, \|fill\| = 0** — R-DISC-031 exactly. Uniform decoration is benign | MEDIUM | REACHABLE-IF-MAILBOX. Not reachable through Gmail's own client in one locale | no — **track**, with the condition in §V |
| **R-MCP-028** | Round 26's `SenderScalar` refusals cost `mailweave_get_attachment` on **ordinary** mail, not only on attacks: an **empty** filename (`is_one_line("")` is `False`) and a filename over **255** characters both give `-32603`. `content/mime.py:32` builds an `AttachmentMetadata` for any part with an `attachmentId`, so an inline image with no filename reaches it. Extends the implementer's N-4, which names only control characters | MEDIUM | REACHABLE-IF-GMAIL; confined to `get_attachment` | no — **track** |
| **R-MCP-029** | `surface/server.py`'s credential clause carries a comment stating that `GmailClient._request` "now wraps its own `access_token()` call", flatly contradicted by `gmail/client.py:450`'s "deliberately **NOT** wrapped". A leftover of the reverted half of R-MCP-017, on the path R-MCP-017 protects | LOW (honesty) | n/a — source comment | no — **track** |
| **R-MCP-030** | `test_the_character_estimate_bounds_the_rendered_result` certifies R-MCP-024's property over a matrix that is **single-source on every one of its ten shapes**, and holds the consequence rather than the inequality, with `if result.is_error: continue`. It is why R-MCP-024 shipped. Same shape as R-DISC-036, one round later, in the other unit | MEDIUM (test strength) | n/a | no — **track**, but fix it with R-MCP-024 or the next estimate change repeats this |
| **R-MCP-031** | The sweep's table omits `Reduction`'s seven wire strings — `detail`, `mime`, `parser`, `stripper`, `charset_used`, `charset_declared`, `header`. `charset_declared` and `mime` come straight off the sender's `Content-Type`; none carries `is_one_line` or a length bound. Not reachable to the mirror today (only `kind` and `removed_chars` are rendered), so the fence holds — but `_every_line_is_one_record` protects only interpolated values, and these are structured-only | LOW | REACHABLE-IF-GMAIL to `structuredContent`; no route to the residue found | no — **track** |

### R-MCP-023 — an ordinary HTML email makes search fail

```
ID:            R-MCP-023
Severity:      HIGH
Reachability:  REACHABLE-IF-GMAIL. Every `multipart/alternative` message - which is the shape
               of essentially all HTML mail - plus three more ordinary shapes.
Fix before demo? YES. The demonstration is "Claude retrieving real mail". This is the first
               thing a real mailbox will do to it, and the answer the owner sees names
               MailWeave as the defect.
Rubric:        MCP-01 (a tool-execution failure reported as a protocol error), MCP-06,
               DISC-03, C-06, I-2.
Location:      server/src/mailweave/envelope/wire.py, `MessageRow.
                 _reductions_have_an_unabridged_path` - refuses `removed_chars == 0 and
                 count in (None, 0)` for EVERY kind.
               server/src/mailweave/content/reductions.py, `Reduction._ZERO_REMOVAL_KINDS` -
                 the exemption list the layer below has and this one does not.
               server/src/mailweave/content/mime.py:190 - ALTERNATIVE_PART_UNUSED is built
                 with `removed_chars=0` and no `count`.
               server/src/mailweave/content/pipeline.py:112 (UNKNOWN_CHARSET, no count),
                 :122 (CHARSET_REPLACEMENTS, count = replacements, which is 0 on a clean
                 fallback), :196 (UNDECODABLE_BODY, no count).
Repro:         /tmp/rmcp26/p15_zero.py - a two-message thread, message 1 a plain
               multipart/alternative with a text/plain and a text/html part:
                 mailweave_search       *** ValidationError: reduction alternative_part_unused
                                        on message Z-001 declares no size  -> JSON-RPC -32603
                 mailweave_get_messages *** the same
               /tmp/rmcp26/p14_charset.py - `Content-Type: text/plain; charset=X`:
                 unicode, cp-1252, x-user-defined, ISO-8859-8-I, UNKNOWN-8BIT,
                 ansi_x3.110-1983  -> search and get_messages both -32603
                 utf-8, us-ascii, iso-8859-1, windows-1252, gb2312, utf8, ""  -> served
               /tmp/rmcp26/p15_zero.py - an undecodable base64 body -> charset_replacements
                 -> the same failure. text/html-only and a bad RFC 2047 encoded-word are fine.
Expected:      a reduction kind the content layer is entitled to emit with no size is a kind
               the row model accepts. `Reduction` names those kinds; `MessageRow` does not
               read the list.
Actual:        the whole response fails. `mailweave_thread_map` still serves, because its rows
               carry no body and therefore no reductions - so the failure is exactly on the
               two tools that disclose text.
Required fix:  one exemption, read from `Reduction._ZERO_REMOVAL_KINDS` rather than restated,
               in `MessageRow._reductions_have_an_unabridged_path`. And a fixture that emits
               `multipart/alternative`, because the reason this survived twenty-six rounds is
               that `tests/fixtures/mailbox.py` never builds one: the unit tests exercise the
               pipeline, which constructs the `Reduction` happily, and the refusal is one
               layer above where they stop.
```

### R-MCP-024 — the character estimate is not an upper bound, and ordinary searches decline

```
ID:            R-MCP-024
Severity:      HIGH
Reachability:  REACHABLE today, shipped defaults, at the client, on every response with more
               than one source.
Fix before demo? YES - as a capability, not as a truth defect. The response declines honestly.
               It declines on the modal demonstration query.
Rubric:        DISC-06 (its mechanism), MCP-01, I-4 (a bad route must not force an empty
               answer), PART-05.
Location:      server/src/mailweave/envelope/measure.py, `SOURCE_STRUCTURAL_CHARS = 1_100` -
                 the per-source scaffolding charge, ~300 characters short per source on my
                 shapes (the implementer's own N-5 records `map_id` alone at 409).
               server/src/mailweave/disclosure/layout.py, `layout_chars` - the docstring
                 states the property this violates.
Repro:         /tmp/rmcp26/p3b_gap.py - estimate vs rendered on the served path:
                 1 source : +269 .. +2,126   (holds)
                 2 sources: -12    3 sources: -268    4: -465    6: -1,502   3(of 12): -1,513
               /tmp/rmcp26/p3_estimate.py - the backstop disabled, so what the ladder alone
                 would serve is measured: 25,081 / 25,319 / 26,314 / 26,375 / 26,196 chars.
               /tmp/rmcp26/p2_search_decline.py - the consequence at the client:
                 3 threads x 3 messages x 90 words -> DECLINED budget_exhausted
                 6 threads x 1 message  x 90 words -> DECLINED
                 30 threads x 1 message x 10 words -> DECLINED
Expected:      layout_chars(layout) >= rendered_chars(render(envelope)).
Actual:        false for every multi-source response; the surface backstop catches it and the
               call returns no mail.
Required fix:  raise `SOURCE_STRUCTURAL_CHARS` against a matrix that varies **source count**,
               and fix R-MCP-030 in the same edit so the next constant is checked on the
               dimension this one was not.
```

### R-MCP-025 — the way out of the decline is a call the server will refuse

```
ID:            R-MCP-025
Severity:      HIGH
Reachability:  REACHABLE today. It is the only affordance on the modal decline.
Fix before demo? YES. Two lines, and without it R-MCP-024 has no recovery at all.
Rubric:        I-2 proof-of-violation (c) - "an affordance that errors ... or is not
               executable by an ordinary MCP client"; C-06; MCP-01; OD-2's "offers a way to
               continue".
Location:      server/src/mailweave/surface/server.py:281-283 - `_narrower_call` mints
                 `budget: {"max_hit_threads": 1}`.
               server/src/mailweave/surface/arguments.py:92 - `BUDGET_KEYS` does not contain
                 it; :353 refuses an unknown key with INVALID_PARAMS.
               server/src/mailweave/surface/server.py:276-279 - the `thread_map` half mints
                 `segment: 0`, and `segment` is inert (R-MCP-012, re-verified).
Repro:         /tmp/rmcp26/p5_affordance.py - follow the affordance the server returned:
                 hop0 declined budget_exhausted, retry_with {"budget":{"max_hit_threads":1}}
                 hop1 JSON-RPC -32602 "unknown budget key 'max_hit_threads'"
               Reached from both `HostCapExceeded` (new this round) and
               `DisclosureLadderExhausted`.
Expected:      `_narrower_call`'s own docstring: "a refusal offering a call that would fail
               again is worse than one offering nothing."
Actual:        that.
Required fix:  either accept `max_hit_threads` in `BUDGET_KEYS` (it is already a published
               `BudgetCapName` and a `Budget` field), or mint a retry out of arguments the
               tool accepts. And a test that **executes** the minted call - no test in the
               suite does, which is why a published affordance and a published argument list
               could disagree.
```

*(R-MCP-026..031 are stated in the table above and evidenced in §1.6, §2.2, §3.3, §3.4, §4.3 and
§7. Each names its file and its probe there; I have not repeated the block form for findings I am
recommending as tracked.)*

---

## Verdict on each of the eight

| # | finding | verdict | on what evidence |
|---|---|---|---|
| **R-DISC-031** | the `Re:` prefix defeats A11 | **fixed** for the shape Gmail sends; **partially** in general | §2.2: `Re:` now behaves as the flat fixture (10/10), a genuinely changed subject still discriminates (10/10), and the defect returns in full on asymmetric decoration outside the 17 markers (0/10, \|fill\| = 0) → R-MCP-027 |
| **R-DISC-034** | `hit_ranks` lacks the all-or-none sweep | **fixed** | §2.3: one function, both callers; a uniform pool now yields a stated zero, not a uniform nonzero |
| **R-DISC-032** | `measure_tokens` charges nothing for `participants` | **fixed** for the field it names | `/tmp/rdisc25/r12_unmeasured.py` re-run: the bound holds at 1→400 senders (was 1.083 at 50, 2.576 at 400). The implementer's own N-2 (14 % under on a withheld-record-heavy response) stands, and my §1.3 table shows the token estimate above the wire on every shape I measured |
| **R-DISC-033** | the rendered result crosses the host cap declaring itself complete | **fixed** as an honesty defect; **not** fixed as a capability | §1.2: no served response crosses 25,000 without `truncated_by`, on any tool or shape I could build. §1.3–1.5: the thing preventing it is the surface backstop, because the ladder's estimate is not a bound → R-MCP-024, R-MCP-025 |
| **R-MCP-020** | three descriptions and SETUP §6 claim the host never truncates | **fixed** | The three `Claim`s now say "never exceeds **either** ceiling … the host's 25,000-character result cap … a response that cannot be brought inside is refused with a narrower call to make". That is true of the response. The final clause is now false of the *retry* (R-MCP-025), which is a new defect and not this one |
| **R-MCP-021** | no character measure on the surface; `_meta` discarded | **partially** | `HOST_RESULT_CHAR_CAP` + `rendered_chars` exist and `declared_result` enforces them (`/tmp/rmcp25/p6_hostcap.py` re-run). `_meta` is still discarded at `on_call_tool` in both directions — the implementer says so, PF-6 owns it, and I agree it is not needed for the demonstration |
| **R-MCP-016** | a sender-chosen filename escapes the fence | **fixed** | §3.1–3.2: the attack produces no served response, 0 disagreements, 0 forged lines, and the blast radius is one tool. §3.3: I could not find another sender-influenced field that reaches the residue. §3.4 and R-MCP-028 are the cost, not a hole |
| **R-MCP-017** | a credential failure reaches the client as `-32603` | **fixed** | §4.1: 8/8 at the client, both producers, all four tools, instruction intact; the mid-request producer re-verified through the round-25 probe. §4.2: R-MCP-006's four-cause diagnosis still holds. §4.3 is a false comment, not a behaviour |

Six fixed, one fixed-as-scoped-with-the-channel-left (R-MCP-021), one fixed as honesty and open as
capability (R-DISC-033), one partial (R-DISC-031). **Nothing the round set out to fix was left
undone, and the exit conditions are met as written.**

---

## V — the one answer

> **No. Not yet — and it is close.**

Not because any of the eight was left undone. They were done, and R-MCP-016 and R-MCP-017 in
particular are done well. It is **no** for three reasons, two of which this round created:

1. **`mailweave_search` fails on ordinary HTML mail** (R-MCP-023). A `multipart/alternative`
   message — the shape of nearly every real email — makes the response model refuse the response
   MailWeave built, and the client is told `-32603 … this is a defect in this server`. So do an
   unknown declared charset and an undecodable body. This is not new this round, but no end-to-end
   fixture has ever had the shape real mail has, so it has never fired. It will fire on the first
   query of a live demonstration. **One exemption list, read from the enum that already states it.**

2. **Ordinary multi-thread searches return no mail** (R-MCP-024), and **the retry offered instead
   is a call the server refuses** (R-MCP-025). A search over three threads of three messages
   declines; so does one over thirty single-message threads. The decline is honest — it says what
   it measured and why — but the affordance beside it is `budget: {max_hit_threads: 1}`, which
   `mailweave_search` rejects with `-32602`. A demonstration where "find my mail about X" answers
   *"budget exhausted, try this"* and the *this* does not parse is worse than a demonstration that
   does not happen. Both are small fixes: one constant, and one line in `BUDGET_KEYS`.

3. **The property the ceiling rests on is not true, and the test that certifies it cannot see the
   dimension it fails on** (R-MCP-024, R-MCP-030). Safety today is held by the backstop at
   `declared_result` and by nothing else. That backstop is real, it is tested, and it works — I
   could not get a single over-cap response past it. But the report says the estimate is never under
   the wire, and it is under the wire on every multi-source response by up to 1,513 characters. A
   claim that is false in the report is a claim someone will rely on.

**What is true, and should be said plainly.** The surface is now *safe*: nothing a sender writes
closed the fence on any probe I could construct — filename, display name, `Reply-To`, `List-Id`,
`Message-ID`, `References`, subject, snippet, `Content-Type; name=` — and the one thing that used to
walk around it is refused with its blast radius confined to one tool. It is now *honest about size*:
no served response crossed the host's cap without saying so, on any shape, on any tool. And a
credential failure now tells the model to run `mailweave auth login` instead of `-32603`, on all
four tools and from both producers. Those are the three things a live demonstration most needed and
they are all there.

What is missing is the ability to survive contact with a real mailbox for one query. Fix
R-MCP-023 and R-MCP-025 — an exemption list and a dictionary key — and raise
`SOURCE_STRUCTURAL_CHARS` with a source-count dimension in its matrix (R-MCP-024, R-MCP-030), and I
would say yes. I would scope that as **four small edits and two tests**, and I would run
R-MCP-023's fixture (a `multipart/alternative` message in `SyntheticMailbox`) through all four
tools before anyone connects a real account.

**Recommended scope, exactly:** R-MCP-023 (one exemption, one fixture), R-MCP-025 (one key or one
minted-argument change, plus a test that executes the affordance), R-MCP-024 + R-MCP-030 (one
constant re-derived on a matrix that varies source count). R-MCP-026 is a one-field honesty
improvement I would take if it is free. **Everything else in the Findings table is track.** Do not
touch N-1, do not touch the 9,000/12,000 figures, do not widen the reply-prefix set for the
demonstration.

---

## Established by execution

* No served `CallToolResult` crossed 25,000 characters without `truncated_by: mailweave` — over
  long single messages, many short ones, 400 distinct senders, 25-recipient lists, 310-character
  addresses, attachments on every message, quoting depth 40, 400-character subjects, twelve-thread
  bulk searches, and all four tools. Measured at a real MCP client.
* At 7 ~110-word messages a thread renders 22,858 characters and serves whole; at 8 it renders
  24,081 with `truncated_by: mailweave` and `partial: true`. When MailWeave cuts, the cut rows are
  a declared collapsed run naming every member with an expansion call, or `withheld` records whose
  `why` names the 25,000-character cap. Nothing was silently dropped on any shape I drove.
* `layout_chars` is below `rendered_chars` on every multi-source response, by 12 to 1,513
  characters; ordinary multi-thread searches therefore decline, and the affordance they hand back
  is refused with `-32602`.
* An ordinary `multipart/alternative` message, an unknown declared charset, and an undecodable
  body each make `mailweave_search` and `mailweave_get_messages` return `-32603`.
* Gmail's own `Re:` no longer makes `subject` message-discriminating; a genuinely changed subject
  still does; `hit_ranks` and `rank` read one function; asymmetric decoration outside the
  seventeen markers restores the defect exactly.
* The filename attack produces no served response, no forged record, no re-attributed body, 0
  disagreements, and does not affect the other three tools. No other sender-influenced field I
  drove reached the wire.
* A refused refresh and a vanished credential store reach the client as `auth_reauth_required`
  with `mailweave auth login`, on all four tools, from both producers; R-MCP-006's four-cause
  startup diagnosis still passes.
* Four of the eight replants (R115, R117, R120, R122) each match exactly one anchor and each
  catcher fails individually, in my own scratch tree.
* All gates clean on the working tree: ruff, ruff format, mypy --strict, `tools.guards`,
  `tools.rubric_status` (6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED), and the test suite.

## False on execution

* **"Never negative — which is the direction that matters"**, and "worst slack +530 characters,
  ratios 1.03 to 1.68" (IMPLEMENTER.md, Part 2, *What I could not establish* item 2). The slack is
  negative on every multi-source response and reaches −1,513. `layout_chars`' own docstring states
  the property as a requirement; it does not hold.
* **`surface/server.py`'s comment** that "`GmailClient._request` now wraps its own `access_token()`
  call". `gmail/client.py:450` says the opposite, and the clause the comment is attached to is the
  only thing catching that condition.
* **R-MCP-012 is not "inert but harmless"** in the sense round 25 filed it: `segment` is still
  inert, and this round made an inert `segment: 0` the `thread_map` narrower retry.
* The implication in the report's N-4 that the `SenderScalar` refusal costs a call only when a
  filename carries a **control character**: an empty filename and a 300-character filename cost it
  too, and both are ordinary mail.
* `docs/ARCHITECTURE_AMENDMENTS.md` gaining "**A12.3**" — there was already an A12.3. The document
  now has two.

## Not establishable here at all

* **Whether real Gmail actually returns the shapes R-MCP-023 needs.** I am confident it returns
  `multipart/alternative` payloads for HTML mail — `content/mime.py` exists to walk them — and that
  `ISO-8859-8-I`, `unicode` and `UNKNOWN-8BIT` appear as declared charsets. I planted them at the
  transport; I did not observe them from the API. **One `messages.get(format=full)` against the
  owner's mailbox settles it, and should be the first call anyone makes.**
* Whether Google's `payload.parts[].filename` can carry a `\n` (round 25 left this open; nothing in
  MailWeave depends on the answer, and it now refuses either way), and whether a real corporate
  gateway in the owner's mail tags inbound only (R-MCP-027's precondition).
* The host's actual cap. 25,000 is `[VERIFIED]` per AD PF-6 in this repository's own record; I read
  the constant, I did not observe a host enforcing it. `_meta["anthropic/maxResultSizeChars"]` is
  still discarded at `on_call_tool`, so the server cannot learn a different figure.
* Anything about live freshness, latency, quota or the OD-7 point-4 comparison. No network, no
  account, and none of it is in this round's scope.
* Whether the demonstration's queries will hit R-MCP-024's decline threshold. That depends on how
  many threads the owner's real queries return and how long their bodies are, and my fixtures are
  smaller than real mail in both id length and body length — which makes my thresholds optimistic,
  not conservative.
