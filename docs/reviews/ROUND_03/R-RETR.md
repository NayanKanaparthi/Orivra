# R-RETR — Round 3 verification (H1b, H2b, R-RETR-001, architectural judgment)

**Reviewer:** R-RETR (fresh instance; did not write this code or Round 2's review). 2026-08-31.
**Method:** execution only, `AGENT_LOOP.md` §4/§7. `HANDOFF.md`/`ROUND_02/R-RETR.md` treated as
claims. Baseline reproduced: `pytest -m "not network"` → **341 passed**; `mypy` clean (61 files);
`tools.guards` clean; `rubric_status.py --check` → 113 NOT TESTED, 0 transitions — matches
`HANDOFF.md`. Round 2's own `/tmp/rretr/` probes re-run **unmodified**. New probes in
`scratchpad/rretr3/`. No project source or test modified.

## Verdicts

| Finding | Verdict |
|---|---|
| **H1b** — `record_shortlist` sealed | **CLOSED**, for the intake it targets |
| **H2b** — 37-ID / 5-of-42 reconstruction | **CLOSED** |
| **R-RETR-001** — collapsed-run dedup (id-level) | **CLOSED**; adjacent gap found — see R-RETR-002 |
| **Architectural claim** (H1 not fully closeable in-process) | **SOUND** |
| **H-sem narrowing** (⊆ H-lex ∪ H-hist) | Correct as coded; **conflicts with AD D.5 as written** |

## H1b — the seal, re-attacked

Round 2's verbatim probes both now raise exactly as claimed (`attack_h1_shortlist_hole.py`,
`attack_h2_via_shortlist.py`: `DispositionInvariantError: shortlisted ids never entered H
through an executed retrieval: [...]`). New attacks (`rretr3/attack_h1b_h2b_batch.py`):

| # | Attack | Result |
|---|---|---|
| 1 | Shortlist mixing 2 real + 1 fabricated id | **Blocked**, names exactly `['smuggled-1']` |
| 2 | Shortlist before its backing page is recorded | **Blocked**; succeeds once retried after a real fetch — correct |
| 3 | `k` inflated to 10,000,000 | Builds — a declared parameter, not a fabrication vector, unchanged by H1b |
| 4 | `k=0`, `k=-5` against a non-empty selection | **Blocked** |
| 5 | Empty page, empty shortlist over empty `H` | Builds — degenerate, not exploitable |
| 6 | Same id via H-lex then H-hist | No double count, first origin wins — correct |
| 7 | Same `FetchedIds` object passed to `record_list_page` twice | **Accepted** — see R-RETR-003 |
| 8 | Subclass `FetchedIds`, override `_release` to ignore the token | **Bypasses `_RECORD_TOKEN` itself** — ids never passed to `__init__` |
| 9 | `record_shortlist` called twice, disjoint selections | Silently replaces the first, no error, no trace |

Attacks 1/2/4/6 confirm the seal holds where claimed. Attack 8 isn't filed separately — it doesn't expand what `HANDOFF.md` §3.1 already concedes — but matters for the judgment below: the token itself, not just the constructor, falls to ordinary subclassing. `test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page` was read, not just run: it walks `disposition.py` with `ast` and confirms `_admit` is the only mutator of `self._origins`, which is what makes 1–7 impossible by construction.

## H2b — end-to-end reconstruction

`/tmp/rretr/attack_h2_via_shortlist.py`, unmodified: raises at `record_shortlist`, before a `Source` or `WithheldRecord` is even built. No route to the same 5-of-42 shape was found that avoids calling `FetchedIds`'s public constructor (architectural judgment, below).

## R-RETR-001 — collapsed-run dedup

`attack_h2_collapsed_dupe.py`, unmodified: `ValidationError, "messages appear in more than one collapsed run: ['d2']"`. The hypothesis test was read, not just run: it generates `included` as the naive sum and asserts either refusal or `included == len(disclosed_ids)`.

**But the fix is narrower than its own rationale.** `_counts_match_the_payload` cross-checks runs by **member id** only; nothing compares **positions**. Two runs with disjoint ids can claim the same slot:
```
run_a = CollapsedRun(positions=(1,5), member_ids=("a1".."a5"), count=5, ...)
run_b = CollapsedRun(positions=(1,5), member_ids=("b1".."b5"), count=5, ...)
Source(thread_id="t1", stated_total=10, included=10, map_id="map-t1-full",
       collapsed_runs=(run_a, run_b))     # builds; accounted_for == stated_total == 10
```
Full `EnvelopeBuilder.build()` succeeds end-to-end (`attack_position_overlap_e2e.py`), one real fetch backing `run_a`, nothing backing `run_b`. Partial overlap ((1,5) vs (3,7)) reproduces identically. The hypothesis generator (`kit.collapsed_run`) advances `positions` by each group's own length, so it can never emit two runs at the same slot — the gap is invisible to the exact test written to close R-RETR-001. Filed as **R-RETR-002**.

## ARCHITECTURAL JUDGMENT — the in-process limit and EV-01

**(a) Reproduced independently:**
```python
ledger.record_list_page(
    FetchedIds(ids=[f"fabricated-{i}" for i in range(37)], page_size=50),
    rung=RungId.L1, query="a call that never happened",
)   # |H| == 37. Zero HTTP calls, zero mocked transport.
```
(`attack_two_line_fabrication.py`.) Flows straight through `record_shortlist` afterward: its provenance check is "is it in H", and H was fabricated one call earlier — H1b's seal does exactly what it claims and nothing more.

**(b) Can any in-process construction do better? No — and it's worse than the writeup says.** `HANDOFF.md` argues a capability token only relocates *who* reaches for a private name. Attack 8 shows more: subclassing bypasses `_RECORD_TOKEN` itself, no reach for the token needed, ids need not even match `__init__`. *Fetcher-only minting* (already the design, `RecordingListTransport`) doesn't help: the fetcher's module and `FetchedIds` are importable by the same code that would forge a page, in the same interpreter — nothing distinguishes "the real wrapper" from "code that imports the same class." *Binding to observed response bytes* fails the same way: whatever verifies the binding is itself importable/patchable code in the same process as the forger. A verifier living inside the thing it verifies isn't one.

Generalized: **a property checkable only by code in the same interpreter as the party being checked is not a security boundary there** — a convention, good against accidents (a rung author who forgets to record a page — the actual shape of R-ORCH-001) and worthless against anyone willing to `import ast`, subclass, or monkeypatch. H1b closes the accident; no successor closes the adversarial case, because that case is defined by "runs in the same process," the one fact no in-process construction changes.

**(c) What the counting proxy must count.** WS-13's acceptance line is "counter cross-check against the harness counting proxy on `http_requests`" — a scalar count. **Necessary, not sufficient.** It catches the shape above (`H` claims ids against `http_requests == 0`). It does **not** catch: one genuine call really returning 5 ids, with a second hand-built `FetchedIds` admitting those 5 plus 32 fabricated ones — `http_requests` still reads "1", and cardinality bounds (`|H| ≤ requests × page_size`) are loose enough to stay under. **Closing EV-01's "bounded above" half needs a content witness, not a count witness**: for every observed `messages.list`/`history.list` call, the proxy must record the **exact id set** returned, and assert `ledger.hit_ids ⊆ (union of ids independently observed this run)`. WS-16 already calls the harness "the sole authority on call counts" and controls the seed account, so it already knows the real id sets — nothing architectural blocks this — **but it is not what WS-13's line currently says.** As written, landing WS-13 lets a reviewer close the count half and believe the content half came with it; it did not. **This is a plan gap, correct it in `IMPLEMENTATION_PLAN.md` now**, or a later round re-discovers this same residual against a finished proxy that still doesn't close it.

**Verdict: the implementer's argument is sound; the round should not be blocked chasing a fix that doesn't exist at this layer.** EV-01 cannot reach in-process PASS on "H bounded above" — not with this design, a stronger token, or subclass-proofing (subclassing isn't the disease; sharing an address space with the party being checked is). Split EV-01 for grading: "H bounded below" — **PASS**, solid against every attack above. "H bounded above" — blocked on WS-13/WS-16 landing **with a content-level cross-check**, not mere existence.

## H-sem ⊆ H-lex ∪ H-hist — breaks WS-08?

**Yes, and as the common case, not an edge case, on AD D.5 as written.** D.5's pool union, priority order: **(a)** threads already touched by L0–L3, **(b)** participant probes (`messages.list` — H-lex, correctly handled), **(c)** most-recent threads in-window — and "each thread costs one `threads.get(format=metadata)` = 40u and yields **all** its message rows" (thread-wise construction, T-RO2). So pool rows for (a)/(c), and non-matching siblings inside (b)'s own threads, arrive via `threads.get` — never H-lex, never H-hist. Priority (a) is listed *first* because those threads are most likely to matter, so the shortlist's winner landing outside both sealed clauses isn't a corner case a refactor might hit — it's what D.5 selects for. When WS-08 lands and stage A/B pick a top-k candidate sourced via (a) or (c), `record_shortlist` will correctly raise on an id that never entered a sealed page. Left alone until then, either WS-08 hits a wall mid-implementation, or — worse — someone under schedule pressure loosens `record_shortlist` again, exactly how H1 was open the first time. **Escalate now**, per `AGENT_LOOP.md` §8 ("a criterion appears unachievable as written, or achievable only by violating another"), as an amendment to AD A.7a/D.5 — not left for WS-08 to discover. Concrete fix, already named in `disposition.py`'s own docstring: give `threads.get`-sourced pool candidates their own sealed intake into `H`, decided by the architecture owner before WS-08 implementation starts.

## New findings

```
ID:            R-RETR-002
Severity:      HIGH
Rubric:        PART-05, R-06, H2's own stated rationale
Location:      server/src/mailweave/envelope/wire.py:437-455 (_counts_match_the_payload)
Reproduction:  rretr3/attack_position_overlap{,2,_e2e}.py
Expected:      "One position, one disposition" (R-RETR-001's own rationale) — no two
               collapsed runs may claim overlapping thread positions.
Actual:        Runs are cross-checked by member id only. Two CollapsedRuns with disjoint
               ids and identical/overlapping `positions` build cleanly; a full map_id-
               bearing Envelope builds end-to-end asserting two 5-message sets both occupy
               the same 5 slots. accounted_for == stated_total throughout, invisible to the
               map check.
Required fix:  Reject any pair of collapsed_runs whose position ranges overlap, alongside
               the id check. Widen R-RETR-001's hypothesis generator to vary positions
               independently of group order — it cannot emit this shape today.
```
```
ID:            R-RETR-003
Severity:      MEDIUM
Rubric:        A.7a scan_scope ("H is defined over the pages actually fetched...")
Location:      server/src/mailweave/envelope/disposition.py:156-164 (FetchedIds._release)
Reproduction:  rretr3/attack_h1b_h2b_batch.py, section 5
Expected:      A page represents one executed call; `recorded` reads as meant for this check.
Actual:        `_release` sets `_consumed=True` but never checks it first. The same page,
               passed to `record_list_page` a second time under a different query, is
               accepted — a phantom ScanScopeEntry claims a second query returned the same
               ids from one real call. H is unaffected (`setdefault` is idempotent);
               scan_scope honesty is not.
Required fix:  `_release` should raise if `self._consumed` is already True.
```
```
ID:            R-RETR-004
Severity:      HIGH
Rubric:        EV-01, WS-08 (AD A.7a, D.5)
Location:      disposition.py's H-sem narrowing vs. ARCHITECTURE_DECISION.md D.5
Reproduction:  Spec conflict, not runtime — WS-08 isn't built; caught pre-implementation
               per AGENT_LOOP §8.
Expected:      H-sem should accept every id AD D.5 will legitimately shortlist once WS-08 lands.
Actual:        D.5 priority (a)/(c) pool candidates arrive via threads.get, never
               messages.list/history.list; (a) is D.5's first-priority source. A legitimate
               top-k draw from either is rejected by record_shortlist.
Required fix:  Architecture-owner decision before WS-08 starts: sealed intake for
               threads.get-sourced pool candidates (extend FetchedIds), or amend AD
               A.7a/D.5 to state which pool sources may back a shortlist.
```

## Execution record

```
uv run pytest -m "not network"                            → 341 passed
uv run mypy                                                 → clean, 61 files
uv run python -m tools.guards                               → clean, 6 sweeps
uv run python tools/rubric_status.py --check                → 113 NOT TESTED, 0 transitions
uv run python /tmp/rretr/attack_h1_shortlist_hole.py         → DispositionInvariantError (H1b)
uv run python /tmp/rretr/attack_h2_via_shortlist.py          → DispositionInvariantError (H2b)
uv run python /tmp/rretr/attack_h2_collapsed_dupe.py         → ValidationError (R-RETR-001)
uv run python rretr3/attack_h1b_h2b_batch.py                  → 9 sub-attacks, table above
uv run python rretr3/attack_two_line_fabrication.py           → |H|=37, 0 HTTP calls
uv run python rretr3/attack_position_overlap{,2,_e2e}.py       → builds through full Envelope
```
All probes under `scratchpad/rretr3/`; none of `server/`, `tests/`, `tools/` modified.

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| **EV-01** | **Split.** Bounded-below: **PASS**. Bounded-above: **cannot PASS in-process** — needs WS-13/WS-16 with an id-content cross-check, not a count cross-check | H1b/H2b close the accident; the adversarial half is out of in-process reach |
| **EV-03** | **NOT YET PASS** | Unchanged since Round 2: `note_withheld` accepts a note for any id in `H` regardless of whether a cap really dropped it; H1's residual still lets a fabricated `H` carry a self-issued note |
| **I-1** | **PASS scoped to accidental under-recording; NOT YET PASS on adversarial fabrication** | Mirrors EV-01's split |
| **PART-05** | **NOT YET PASS** | R-RETR-002: end-to-end violation of "one position, one disposition" — R-RETR-001's own rationale, at the position level |
| **DISC-06** | **Not re-verified this round** — out of scope, R-DISC's gating item, as Round 2 also deferred it | No change to `response.py`'s self-truncation check in this diff |
