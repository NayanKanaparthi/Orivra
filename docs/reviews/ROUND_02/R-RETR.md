# R-RETR — Round 2 verification (H1, H2)

**Reviewer:** R-RETR (fresh instance; did not write this code). **Date:** 2026-08-31.
**Method:** execution only, per `AGENT_LOOP.md` §4/§7. `HANDOFF.md` treated as claims, not
evidence. Baseline reproduced: `uv run pytest -m "not network"` → **297 passed**, matching the
handoff. All probes below live in `/tmp/rretr/`; no project source or test file was modified.

## Verdicts

| Finding | Verdict |
|---|---|
| **H1** — transport owns ledger recording | **PARTIALLY CLOSED** |
| **H2** — a claimed map accounts for every message | **PARTIALLY CLOSED** |

---

## H1 — attacks against the seal

`envelope/disposition.py::FetchedIds` + `retrieval/transport.py::RecordingListTransport`,
attacked directly (`/tmp/rretr/attack_h1.py`, `attack_h1_shortlist_hole.py`):

| # | Attack | Result |
|---|---|---|
| 1 | Original R-ORCH-001 probe: fetch 100 via transport, disclose only 10 | **BLOCKED** — `DispositionInvariantError` naming all 90 unaccounted ids |
| 2 | `record_list_page(bare_list, ...)` — old-shape call | **BLOCKED** (`AttributeError`, since a `list` has no `_release`; ugly but effective) |
| 3 | `page._release(forged_token)` | **BLOCKED** — `DispositionInvariantError` |
| 4 | Fetcher returns `list[str]` instead of `FetchedIds` | **BLOCKED** by the transport's `isinstance` check |
| 5 | Caller holds the raw fetcher, calls it directly, never hands the page to a ledger | Page obtained but **unreadable** (no `__iter__`, no `__getitem__`); ids never enter H but also never leak — matches the module's own disclosed residual risk |
| 6 | Subclass `FetchedIds` to add a public accessor | Subclass can read its own `_ids`, but `record_list_page` still consumes exactly what `_release` returns — cannot report fewer | 
| 7 | Reach `page._ids` / import `_RECORD_TOKEN` directly | Succeeds — the **documented, acknowledged** private-name exception, same as `_MINT_TOKEN` in Round 1 (R-ORCH-002 pattern). Not a new defect. |

**Verdict on H-lex/H-hist: solid.** Every attack that goes through `messages.list` /
`history.list` recording is now structurally blocked, exactly as claimed.

### The unsealed clause — demonstrated concretely (critical, per work order)

`DispositionLedger.record_shortlist(*, ids: Iterable[str], rule: str, k: int)` still takes a
bare list. Confirmed with zero transport calls:

```
ledger.record_shortlist(ids=[f"fabricated-{i}" for i in range(50)], rule="i-made-this-up", k=50)
# -> |H|=50, all H-sem, none backed by any FetchedIds page
```
(`/tmp/rretr/attack_h1_shortlist_hole.py`). `certify()` still requires a withheld note per
undisclosed id, so a bare fabrication alone does not silently vanish — but nothing stops the
attacker from filing that note themselves (see H2 below). `record_shortlist` is untested for
provenance: `grep -rn record_shortlist tests/` shows only k-limit and pool-declaration tests,
never a check that shortlisted ids trace to any real retrieval.

**Regression check (H1):** reintroduced the round-1 shape (`record_list_page` accepting a bare
`Iterable[str]`) in a `/tmp` copy of the tree (`/tmp/rretr/defect_h1/`, not the project). Result:
5 of 9 tests in `test_transport_seam.py` fail, including
`test_under_recording_now_raises_instead_of_certifying_a_shrunken_hit_set` (the direct
R-ORCH-001 regression test). Restoring the fix returns the suite to green. The test genuinely
discriminates.

---

## H2 — attacks against map completeness

`envelope/wire.py::Source` + `envelope/response.py::Envelope`, attacked directly
(`/tmp/rretr/attack_h2_defeats.py`):

| # | Attack | Result |
|---|---|---|
| 1 | Inflate `stated_total` with no added accounting (`stated_total=1000`) | **BLOCKED** |
| 2 | `CollapsedRun(count=10, member_ids=<3 ids>)` | **BLOCKED** by `CollapsedRun`'s own validator |
| 3 | Same id as both a row and a collapsed-run member | **BLOCKED** — `"messages both present as rows and inside a collapsed run"` |
| 4 | `withheld_here` names an id with no backing `WithheldRecord` | **BLOCKED** at `Envelope` assembly (confirmed via the project's own `test_a_map_cannot_close_its_arithmetic_with_a_withheld_record_that_does_not_exist`, re-run) |
| 5 | Omit `map_id` while `included == stated_total` | Builds — correctly not a map claim; no downstream code reads a mapless `Source` as exhaustive. Not a new gap; `stated_total`'s honesty against live Gmail data remains the pre-existing, already-tracked PART-01 gap. |
| 6 | **Same id duplicated across two different `collapsed_runs`** | **NOT BLOCKED — new defect, see R-RETR-001** |

### R-RETR-001: confirmed by full `Envelope.build()`

`run_a=["d1","d2"]`, `run_b=["d2","d3"]` (d2 repeated across runs), only `d1/d2/d3` ever
recorded via a real `messages.list` call. `Source(stated_total=4, included=4, map_id=...,
collapsed_runs=(run_a, run_b))` builds, and the **full envelope builds end-to-end**
(`/tmp/rretr/attack_h2_collapsed_dupe.py`): `included=4` (naive sum of run lengths) equals
`stated_total=4`, the map reports 100% complete, but `envelope.disclosed_ids` contains only 3
distinct ids. A 4th real thread message could be silently missing with **no accounting at
all** — exactly the shape H2's acceptance criterion forbids ("constructing a map that omits a
message with no accounting must raise"), and it does not raise.

Cause: `wire.py::Source._counts_match_the_payload` (line 425) computes
`collapsed_members = sum(len(run.member_ids) for run in self.collapsed_runs)` — a naive sum,
never deduplicated across runs — and `_a_claimed_map_accounts_for_every_message` (line 470)
trusts `accounted_for`, which is built from that same sum. The existing overlap check (line
429) only compares row ids against the union of collapsed members; nothing compares collapsed
runs against each other.

### Chained defeat via H1's shortlist hole (demonstrated end-to-end)

Built a full `Envelope` reproducing R-DISC-001's exact 5-of-42 shape, but "closed": 5 real rows
(from a genuine `messages.list` fetch) + `map_id="map-t1-full"` + `stated_total=42` +
`withheld_here=<37 ids>`, where the 37 ids were injected into H purely via
`record_shortlist(ids=<37 fabricated strings>, ...)` and given self-issued `note_withheld`
entries (`/tmp/rretr/attack_h2_via_shortlist.py`). The envelope **built successfully** —
`Source.accounted_for == 42`, all 37 withheld records present and correctly cross-checked
against the certificate, because every check the round-2 fix added is satisfied once H itself
is fabricable. This is the implementer's own disclosed "weakest spot" (HANDOFF §4.1),
confirmed here by execution rather than by reading the claim, and it is a live defeat of H2's
map-completeness guarantee, not just of H1 in isolation.

**Regression check (H2):** reintroduced round-1 (removed `_a_claimed_map_accounts_for_every_message`
entirely) in `/tmp/rretr/defect_h2/`. Result: exactly the 2 tests that assert map completeness
fail — `test_a_claimed_map_that_omits_most_of_the_thread_is_unconstructible` (the literal
R-DISC-001 reproduction) and `test_a_map_may_account_for_a_message_as_a_stub_a_collapsed_run_or_a_withheld_record`
— nothing else breaks. Restoring the fix returns the suite to green. Genuinely discriminating.

---

## New findings

```
Finding:       R-RETR-001
Severity:      HIGH
Rubric:        PART-05, H2's own acceptance criterion (contract R-06)
Location:      server/src/mailweave/envelope/wire.py:425 (`_counts_match_the_payload`),
               :470 (`_a_claimed_map_accounts_for_every_message`)
Reproduction:  /tmp/rretr/attack_h2_collapsed_dupe.py — two CollapsedRuns sharing one member
               id, full EnvelopeBuilder.build()
Expected:      "Constructing a map that omits a message with no accounting must raise"
Actual:        Builds cleanly. `included`/`accounted_for` sum collapsed-run member counts
               without deduplicating across runs, so a duplicated id inflates the count by
               one per repetition; a map can report 100% completeness while a real message
               is unaccounted for anywhere.
Required fix:  Compute collapsed_members from the deduplicated union of member ids across all
               collapsed_runs (as Source.disclosed_ids already does), not from summed lengths,
               and reject any id appearing in more than one collapsed_run.
```

The record_shortlist gap and its H2 consequence are not filed as a new finding — they are the
implementer's own disclosed gap (HANDOFF §0, §4.1), verified here by execution rather than a
new discovery.

---

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| **EV-01** (hit containment, incl. H-sem) | **NOT YET PASS** | H-lex/H-hist clauses solid; H-sem's `record_shortlist` still accepts unprovenanced ids — EV-01(i)'s "declared, not shrinkable" guarantee only bounds size (`≤k`), not authenticity |
| **EV-03** (withheld discipline) | **NOT YET PASS** | `note_withheld` accepts a cap/why/affordance for any id in H regardless of whether a cap genuinely dropped it — unchanged from Round 1, now more consequential because H-sem is fabricable |
| **I-1** (evidence preservation) | **NOT YET PASS overall; recommend PASS scoped to the H-lex/H-hist clauses** | those two clauses are structurally airtight (attacks 1–4 above); the ledger's H as a whole is only as trustworthy as its least-sealed clause |
| **PART-05** (unexpanded content visible as stubs) | **NOT YET PASS** | R-RETR-001 is a direct, demonstrated violation of this criterion's mechanical guarantee, independent of H1; the shortlist-chain attack is a second, independent way to defeat it |
| **DISC-06** (self-truncation vs. ceiling) | **Not independently verified this round (R-DISC's gating item)** — light read of `response.py::_self_truncation_is_verified_against_the_ceiling` shows the described two-part check (fits ceiling regardless of claim; claim requires a real ladder artifact) present and matching the handoff; deeper adversarial testing left to R-DISC |

## What held up well

The core inversion — `withheld := H − disclosed`, and now `map_id` completeness derived from
enumeration — resisted every direct attack on its own terms: inflated totals, malformed
collapsed runs, phantom withheld records, and row/collapsed-run overlap are all refused with
specific, actionable error messages. The transport seal (`FetchedIds`) is a genuine structural
improvement over Round 1 for the two clauses it covers. Both gaps found here are narrow and
already either disclosed (H-sem) or newly pinpointed with an exact fix (R-RETR-001) — this is
incremental hardening work, not a redesign.
