# R-DISC — Round 5 verification (R-DISC-002..007, amendments A3/A4)

**Reviewer:** R-DISC (fresh instance; did not write this code, `HANDOFF.md`, or the Round-1
report). 2026-08-31. **Method:** execution only, `AGENT_LOOP.md` §4/§7. `HANDOFF.md` treated
as claims, not evidence. Baseline reproduced independently: `make check` → ruff/format/mypy
clean (62 files), `pytest -m "not network"` → **557 passed**, 7 guards clean,
`rubric_status.py --check` → 7 PASS / 106 NOT TESTED / 9 transitions — matches `HANDOFF.md`
exactly. For every "genuinely fixed" claim below, the defect was **reintroduced in the actual
source file** (backed up, diffed byte-identical after restore, suite re-run green), not merely
re-read. Probes in `scratchpad/rdisc5/`. No project source or test left modified.

## Verdicts

| Finding | Verdict | Evidence |
|---|---|---|
| R-DISC-002 ceiling bypass via `mark_self_truncated` | **CLOSED** | reintroduced; 3 tests → `DID NOT RAISE`; live 27k/9k repro fails closed |
| R-DISC-003 partiality after bulk content | **CLOSED** | order now `partial, withheld, retrieval_report` before `sources`; verified on a rebuilt realistic envelope |
| R-DISC-004 8/10 renderers, OD-3 untested — blocks PART-07 | **CLOSED** | 50/50 tests; reintroduced 2 planted defects, exactly 3 fail; all 10 kinds/7 roles/OD-3 built end-to-end |
| R-DISC-005 `fetched_at` any string | **CLOSED** | RFC-3339+offset+ordering enforced; attacked with 17 edge cases |
| R-DISC-006 `constraint_coverage` unvalidated | **CLOSED** | both levels reintroduced independently, 2 tests fail each |
| R-DISC-007 / amendment A4 `included` arithmetic ruling | **PARTIALLY CLOSED** | ruling is sound; its own "what changes" promise was never executed — R-DISC-008 |

## R-DISC-002 — self-truncation ceiling bypass

`response.py:274`'s validator now measures the assembled payload unconditionally and requires
a degradation-ladder artifact behind any `truncated_by=mailweave` claim. Reintroduced Round-1's
exact bug (`if self.truncated_by is not None: return self`, ahead of the ceiling check) —
3 tests broke, and a live rebuild of the 27,000-vs-9,000 repro shipped `measured=27000` against
`ceiling.applied=9000`. Restored, diffed clean, `make check` green.

## R-DISC-003 — field order, judged as a consuming agent

Rebuilt Round 1's scenario (decision-reversal thread, OD-3 stubs, collapsed run, a second
thread capped/withheld, `outcome=inconclusive` with an untried L6). Byte offsets in the real
JSON: `partial` **395**, `withheld` **414**, `retrieval_report` **830**, `sources` (bulk
content) not until **2127**, of 5,677 total. **Judgment: real, material improvement.** A
top-to-bottom reader hits `partial`/`withheld`/not-tried in the first 15% of the document,
before any message body. Minor residual: `truncated_by` is still the last field, after
`sources` — not blocking, since `partial` already carries the signal that matters.

## R-DISC-004 — scrutinised hardest (blocks PART-07)

`test_reason_coverage.py`, 50/50 pass. Confirmed directly: completeness check fails an 11th
unlisted kind; all 10 `.render()`s non-empty/non-decorative; **every parameter of every reason
mutated, render must change** — reintroduced 2 planted defects (`SnippetContains` → constant
decorative string, `WindowOffset` dropping `offset`), got exactly the 3 predicted failures;
distinctness across kinds; full wire round-trip. **OD-3 floor**: a real `MATCHED` reversal row
plus reply parent/child as `STUB` rows, built through an actual ledger + builder — disclosed
not withheld, each names why, working `unabridged` affordance, role/depth independence proven
(`PARENT` promotable to `body_clean`). All 7 roles built. Restored clean; suite green.

**PART-07 nuance**: rubric maps it to **P4 + P6**. R-DISC-004 fully closes P4 (structural
role/reason correctness). **P6** (live selection-provenance labelling) needs agent-in-the-loop
infra this round lacks. Not yet promotable, but for a new reason: only P6 blocks it now.

## R-DISC-005 — attacked with malformed offsets, leap seconds, extremes

17 cases: `+25:00`/`-99:00`/`+24:00`, leap second `23:59:60`, naive datetime, date-only,
month-13, unicode-suffix — all correctly **rejected**. Far-future (`9999`)/far-past (`0001`)
**accepted**, deliberate ("not in the future" would tie validity to clock skew).
`verified_at < fetched_at` rejected; `verified_at` 50yr **after** `fetched_at` accepted —
consistent with the stated scope (ordering only). **Minor residual**: `+0000` (no colon)
accepted though RFC 3339 requires one — label stricter than what's enforced → R-DISC-010.

## R-DISC-006 — both levels reintroduced

Row-level (`wire.py`, unnamed/duplicate constraint names) and envelope-level (`response.py`,
coverage of a constraint `asked_for` never carried) disabled independently — 2 tests fail each
(`DID NOT RAISE`). Restored, diffed clean, suite green. **CLOSED at both levels.**

## R-DISC-007 / amendment A4 — the ruling exists, but was not carried through

A4 rules R-05 correct (`included=42`, subset reading) and states explicitly it changes
**"`ARCHITECTURE_DECISION.md` §D.2's worked example only"** and that **"the Round 5 test...
docstring is updated to record that the ruling now exists rather than that it is owed."**
Verified against the files: **neither happened.** `ARCHITECTURE_DECISION.md:1069` still reads
`"included": 7, "included_as_stub": 35` — the exact reading A4 says it corrects.
`test_envelope_contract.py:1456`'s header still says "pinned pending a ruling," and its
docstring still says *"neither has a ruling on record"* / *"if the ruling goes the other
way..."*. `wire.py:513`'s docstring cites only "the round-1 handoff," no mention of A4. A
reviewer running this suite today would conclude the question is still open — it is not. The
ruling itself is sound (the ledger's own "a stub is disclosed, not omitted" invariant already
forces the subset reading). **Verdict: PARTIALLY CLOSED** — substantively answered, but A4's
own accountability claim about what it edited is false in three places. → R-DISC-008.

## §4 — New findings

```
ID:            R-DISC-009
Severity:      HIGH
Rubric:        PART-05, R-06, amendment A3
Location:      disposition.py::note_withheld (thread_id param, unchecked); ::HitOrigin.thread_id
               (written, never read); wire.py::_a_claimed_map_accounts_for_every_message (count-only)
Reproduction:  probe_a3_mislabeled_thread.py — observed 4 real ids for thread t1 via
               `record_thread`, 1 real id ("t2-only") for unrelated t2. Disclosed 4 t1 rows.
               Called `note_withheld(message_id="t2-only", thread_id="t1", ...)` — false;
               t2-only was observed under t2, never t1. Built Source(thread_id="t1",
               stated_total=5, map_id="mw1.fake", messages=<4 rows>, withheld_here=("t2-only",)).
Expected:      A3 + the map-completeness validator guarantee a `map_id`-bearing, occupancy-
               checked source genuinely enumerates the thread it claims (PART-05).
Actual:        Builds cleanly, `accounted_for == stated_total == 5`. The envelope-level check
               only compares `record.thread_id == source.thread_id` against the caller-supplied
               thread_id — never `HitOrigin.thread_id`, the thread actually observed via
               threads.get. t1's map "accounts for" its 5th message by borrowing a real id
               belonging to a different thread. Not adversarial-only: a caller-side bug (wrong
               thread_id in a loop over threads) produces this silently.
Required fix:  When `HitOrigin.thread_id` is not None, require note_withheld's/certify's
               thread_id to match it; raise otherwise — A3's principle extended to identity.

ID:            R-DISC-008
Severity:      MEDIUM
Rubric:        R-ARCH-008/R-DISC-007's own closure obligation; AGENT_LOOP §9
Location:      ARCHITECTURE_DECISION.md:1069; test_envelope_contract.py:1456-1476; wire.py:513
Reproduction:  Read all three after locating A4 in ARCHITECTURE_AMENDMENTS.md.
Expected:      A4's "What changes": D.2's example corrected; pinning test's docstring updated
               to say a ruling exists.
Actual:        All three still read as before A4 — D.2 shows `included=7`; the test still says
               "pinned pending a ruling"/"neither has a ruling on record"; wire.py cites only
               "the round-1 handoff." A4 makes a specific, checkable claim and it is false —
               same failure mode as R-ARCH-008/R-DISC-007 sitting open four rounds, one level
               down: the record exists but wasn't propagated to the places it names.
Required fix:  Update D.2's example to `included=42, included_as_stub=35`; update the test's
               header/docstring and wire.py's docstring to cite A4 as settled.

ID:            R-DISC-010
Severity:      LOW
Rubric:        R-08
Location:      wire.py::parse_instant
Reproduction:  `"2026-08-30T14:02:11+0000"` (no colon) — accepted via `datetime.fromisoformat`.
Expected:      Docstring/errors say "RFC 3339 instant."
Actual:        RFC 3339 §5.6 requires a colon in the offset; this is ISO-8601 basic format, not
               RFC 3339. Still unambiguous/comparable, so R-08's real obligation holds — only
               the label is stricter than what's enforced.
Required fix:  Loosen the label to "offset-bearing ISO-8601 instant," or add a colon check.
```

## Amendment A3, re-attacked

Restated Round 4's proof (`stated_total=5`, run at `(900,904)`) and R-ARCH-013's single-row
version against current code — both still raise, unchanged. **What defeats "complete map" is
not a position number — it's identity**: withheld records carry no position, and the thread a
withheld id is charged against is caller-asserted, never checked against where it was actually
observed (R-DISC-009). A3 genuinely closed the *numeric* half; it never claimed to close the
*identity* half.

**The flagged Round-4 property diff**, verified rather than trusted: reintroduced the
R-RETR-002 defect (disabled the occupancy-clash check) and re-ran the property — it **failed
immediately** (`1 == 2`) in the **success branch**, untouched by A3. The widened refusal-branch
`or` only affects which of two legitimate causes an *already-refused* example is attributed to;
a broken occupancy check moves the example into the success branch instead, where the assertion
still catches it. **Judgment: still genuinely tested; implementer's characterization accurate.**

## What an agent actually sees

Rebuilt Round 1's scenario against current code (`build_realistic_r5.py`). First bytes:

```json
{
  "schema_version": 2, "fence_nonce": "mw-d1b641bf5bdfaa83", "asked_for": {...},
  "partial": true,
  "withheld": [{"id": "m99", "thread_id": "t2", "cap": "max_hit_threads",
    "why": "13 hit-bearing threads found; max_hit_threads=12, t2 ranked 13th by recency",
    "affordance": {"tool": "mailweave_search", "args": {...}}}],
  "retrieval_report": {"outcome": "inconclusive", ...,
    "not_tried": [{"rung": "L6", "why": "budget", "affordance": {...}}]},
```
`sources` (message bodies) doesn't start until byte 2127 of 5677 — versus Round 1, where it
was third and a reader met 60% of the payload before any partiality signal. An agent reading
linearly now learns the response is partial, what's withheld/why, and what wasn't tried,
before a single message body.

## Criterion recommendations

| Criterion | Recommendation | Why |
|---|---|---|
| PART-01 | Not yet PASS (unchanged) | needs GMAIL-03 against real `threads.get`; out of scope |
| PART-02 / PART-03 | Stay PASS | untouched this round |
| PART-04 | Not yet PASS (unchanged) | needs a live MCP server + P-follow driver |
| PART-05 | **Not yet PASS — new blocker** | numeric guarantee (A3) holds; R-DISC-009 shows completeness still defeatable via thread-identity mislabelling |
| PART-06 | Not yet PASS (unchanged) | needs pinned agent-in-the-loop runs; R-DISC-003 helps but doesn't move this alone |
| PART-07 | **Recommend PASS for the P4 (structural) half** | R-DISC-004 closes it fully; full criterion NOT TESTED pending P6, unrelated to this fix |
| DISC-06 | **Structural half ready; full PASS needs R-MCP** | ceiling-vs-claim now genuinely enforced and reintroduction-tested; rubric also needs a live oversized-thread interop case |

## Execution record

```
make check                                  → clean; 557 passed; 7 guards; 7 PASS/106 NOT TESTED
pytest tests/test_reason_coverage.py        → 50/50
Reintroduced+reverted (diffed byte-clean, suite re-green after each):
  response.py ceiling-flag bypass           → 3 tests fail (R-DISC-002)
  reasons.py  2 planted renderer defects    → 3 tests fail (R-DISC-004)
  wire.py/response.py constraint_coverage row+env checks → 2 tests fail each (R-DISC-006)
  wire.py     occupancy/clash check         → property fails on 1st example (A3 diff)
probe_002_reintro.py          → live 27k/9k repro ships under the reintroduced bug
probe_005_timestamps.py / _source.py → 22 fetched_at/verified_at edge cases, all as expected
probe_a3_mislabeled_thread.py → BUILDS: mislabelled-thread map-completeness defeat (R-DISC-009)
build_realistic_r5.py         → full realistic envelope, byte offsets for R-DISC-003
```
All probes: `scratchpad/rdisc5/`. Baseline and post-probe `make check` both clean; no project file left modified.
