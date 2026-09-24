# R-ARCH — Round 4 Architecture & Code-Quality Review

**Reviewer:** R-ARCH (fresh instance; did not write this code, `HANDOFF.md`, or any prior
review). 2026-08-31. **Method:** execution only (`AGENT_LOOP.md` §4/§7); `HANDOFF.md` and
`RUBRIC_TRANSITIONS.md` treated as claims, cross-checked against the four cited Round 1–3
reviewer reports and against re-running the code. Baseline reproduced: `ruff check`/`ruff
format --check` clean (87 files), `mypy` clean (61 files), `pytest -q -m "not network"` →
406 passed, `python -m tools.guards` clean, `rubric_status.py --check` → 9 PASS / 104 NOT
TESTED / 9 transitions. Probes under `scratchpad/rarch4/`; no project source or test file in
`/root/mailweave` modified — all adversarial edits were made to a throwaway copy in `/tmp`.

## VERDICT ON THE ORCHESTRATOR'S TEST EDIT (Priority 1)

**A legitimate strengthening, not a relaxation — but "genuinely stronger" needs one caveat,
and I found the real-world instance of that caveat in the wild.**

`test_no_criterion_is_currently_claimed_as_pass` asserted a snapshot (zero PASS) that is
structurally incompatible with the loop doing its job: the moment one reviewer legitimately
promotes one criterion, the assertion is false forever after, regardless of legitimacy. It
is not an invariant the project can hold to at any interesting point in its life — it is a
tripwire that fires exactly once, on the first correct promotion. `WS-19`'s own Round-1
review (`ROUND_01/R-ARCH.md:24`) recorded the rubric at "0 PASS" the moment this test was
written; R-DISC's and R-SEC's own Round-1 reports then recommended seven of the nine
promotions later credited to Round 1 — the scenario the old test could not survive. Treating
it as a permanent regression guard was already a category error before Round 4 touched it.

`test_every_passing_criterion_was_moved_by_a_reviewer_with_evidence` asserts the rule
AGENT_LOOP §1/§6 actually states — every PASS traces to a transition row from a §2.3
reviewer domain carrying non-empty evidence — as a standing invariant that holds for any
number of legitimate promotions, not just zero. I tried to defeat it directly (probes in
`scratchpad/rarch4/run_defeats.py`, run against a scratch copy of the real rubric with EV-01
flipped to PASS):

| Attack | `check()` | the new test | Caught |
|---|---|---|---|
| Fabricated reviewer domain (`R-FAKE`) | flags | flags | **yes** |
| Orchestrator self-signs outside §2.3 (`R-ORCH`) | flags | flags | **yes** |
| Empty evidence field | flags | flags | **yes** |
| Whitespace-only evidence field | flags | flags | **yes** |
| `-` evidence (existing case) | flags | flags | **yes** |
| PASS criterion, transition row targets a non-PASS status | flags | flags | **yes** |
| Row naming a criterion that does not exist | flags | flags (indirectly: EV-01 stays unbacked) | **yes** |
| Duplicate identical legitimate row | — | — | not a defect; idempotent |
| **Legitimate-domain row, plausible but fabricated evidence text (cites a test that does not exist)** | **clean** | **clean** | **no** |

Every *structural* forgery is caught, including attacks the work order didn't list
(wrong-target-status row, unknown-criterion row). The one attack that gets through is
substantive, not structural: a row signed by a real reviewer domain with non-empty,
plausible-looking evidence text that does not actually establish the claim. Neither the old
test nor `check()` (the real CI gate, `make gate`) could ever have caught that either —
verifying cited evidence is *true* is a reviewer's job, not a markdown-parser's, which is
why AGENT_LOOP puts an adversarial pass at the release gate (§2.4). The orchestrator's edit
neither introduces this gap nor closes it; it formalizes the half a script can enforce.

**That gap is not hypothetical here.** Cross-checking all nine promotions in
`RUBRIC_TRANSITIONS.md` against the four cited Round 1–3 reports: **seven are clean,
unqualified matches** (PART-02, PART-03, ROUTE-01, NFR-01, NFR-04, REG-04 — all "Recommend
PASS"/"PASS" with no hedge in their source report; SEC-04 — "PASS-ready on atomicity",
matching). **Two overreach**, exactly the two named in this round's brief:

- **INJ-04.** The criterion is "HTML pipeline: visible text, flagged hiding, no network."
  Round 3's own recommendation was explicit: *"Ready for PASS on the bidi/zero-width scope
  specifically"* (`ROUND_03/R-SEC.md:185`) — scoped, partial. The ledger row records an
  unqualified `PASS` and cites *only* Round 3 evidence about RLO/zero-width stripping in
  **Subject, From, and attachment filenames** — none of which is the HTML body pipeline.
  The rest of the acceptance text (hidden constructs removed with `hidden_content_removed`,
  sockets-disabled proof) *was* substantively tested — Round 1 R-SEC (display:none/
  visibility:hidden/comment stripping) and Round 2 R-SEC (H4: depth/size caps, no silent
  loss) — but the row cites neither, so the ledger's own evidence trail doesn't establish
  what it certifies. See R-ARCH-009.
- **PART-07.** Round 1 R-DISC's recommendation was explicit: *"Recommend PASS (structural
  half only) ... mark the coverage half not-yet-PASS"* (`ROUND_01/R-DISC.md:238`) — 8 of 10
  `ReasonKind` renderers are never constructed by any test, and the round's headline OD-3
  reply-parent/child-stub shape is untested (R-DISC-004, MEDIUM, still **open**). The rubric
  shows a flat `PASS` with no qualifier, and no R-DISC reviewer has run since Round 1 to
  re-test the deferred half — Rounds 2–4 fielded no R-DISC domain review at all. See
  R-ARCH-010.

Neither overreach is something the new test was ever built to catch (both rows are
domain-signed with genuine, non-empty evidence text) — they are consolidation-discipline
defects (AGENT_LOOP §5 step 5), not test-mechanics defects, and they predate Round 4 by one
and three rounds respectively. I am not treating them as evidence the orchestrator's *test
edit* was self-serving; I am treating them as evidence the mechanical gate was never
sufficient alone, which is exactly why this priority exists.

**Bottom line:** the test edit itself did not weaken anything a reviewer should have been
relying on — `check()`/`make gate` carried the real enforcement before and after, and the
new test is a correct, adversarially-verified formalization of the rule the placeholder was
gesturing at. What deserves scrutiny is not this test, but the two consolidation rows it
structurally cannot see through.

---

## Findings

**R-ARCH-009 · HIGH**
Rubric: INJ-04 (M) — process, AGENT_LOOP §5/§6
Location: `docs/reviews/RUBRIC_TRANSITIONS.md` (INJ-04 row); `docs/RELEASE_RUBRIC.md:139`
Reproduction: compare the INJ-04 row's evidence text against `ROUND_03/R-SEC.md`'s own
per-criterion line ("Ready for PASS on the bidi/zero-width scope specifically") and against
`ROUND_01/R-SEC.md`'s execution record (display:none/visibility:hidden/comment stripping,
HIDDEN_CONTENT flag) and `ROUND_02/R-SEC.md`'s H4 verdict (depth/size caps CLOSED).
Expected: an evidence field that "names the reproduction" (file's own header) for the
criterion actually being certified.
Actual: the row cites only the bidi/zero-width work and omits the two prior rounds' evidence
that covers the rest of the acceptance text. A reader of the ledger alone cannot verify
hidden-construct removal or the no-network claim for INJ-04's stated scope.
Required fix: rewrite the row to cite all three rounds' relevant evidence, or re-open INJ-04
until a single reviewer pass re-verifies the full acceptance text in one report.

**R-ARCH-010 · HIGH**
Rubric: PART-07 (M) — process, AGENT_LOOP §5/§6
Location: `docs/RELEASE_RUBRIC.md:103,786`; `docs/reviews/ROUND_01/R-DISC.md:238,73-84`
Reproduction: `grep -c 'GmailQueryMatch\|ThreadMember' tests/` vs. the other 8 `ReasonKind`
variants in `server/src/mailweave/envelope/reasons.py` — unchanged since Round 1;
`R-DISC-004` carries no closing round in any later HANDOFF or report.
Expected: a mandatory criterion's rubric status reflects what was actually verified, or
names what remains open the way the transitions-row prose does for PART-07 specifically.
Actual: the rubric's summary/detail tables show unqualified `PASS`; `gate_blockers()` treats
it as fully satisfying the mandatory flag. The reviewer who promoted it explicitly withheld
the coverage half, and nobody in three subsequent rounds picked that half back up.
Required fix: either schedule an R-DISC pass to close R-DISC-004 and reconfirm PART-07 in
full, or add a rubric-level annotation distinguishing "structurally PASS" from "behaviourally
verified" so `gate_blockers()` and a future release decision see the real state.

**R-ARCH-011 · HIGH**
Rubric: none — process, AGENT_LOOP §9 ("Records")
Location: `docs/reviews/FINDINGS_LEDGER.md`
Reproduction: `wc -l docs/reviews/FINDINGS_LEDGER.md` → 48 lines, findings table **empty**.
Expected: "every finding ever raised, with status and closing evidence" (file's own header);
§9's regression obligation requires a populated `Regression test` column per closed HIGH.
Actual: zero rows for the 30+ findings raised across Rounds 1–4 (R-SEC-001..020,
R-DISC-001..007, R-RETR-001..005). The only record of any finding's status is round-report
prose — not cross-checked, not queryable, and (R-ARCH-009/010) not always consistent from
one round's citation to the next.
Required fix: populate the ledger from the four rounds' reports (retroactive filing is
fine), or amend AGENT_LOOP §9 rather than leave a mandatory record unmaintained.

**R-ARCH-012 · MEDIUM**
Rubric: none — test-quality / gate-reliability (AGENT_LOOP §7.2)
Location: `tools/rubric_status.py::check`; `tests/test_rubric_status.py`
Reproduction: see the defeat table above — a domain-signed row citing a nonexistent test
passes both `check()` and the new unit test cleanly.
Expected/Actual: a structural ceiling of a markdown-parsing gate — neither mechanism can, or
was ever going to, verify cited evidence is real. Not a bug in this round's edit.
Required fix: none owed this round. Recommend one sentence in `rubric_status.py`'s docstring
stating the residual explicitly (mirroring `FetchedIds`' own "not closed here" disclosure),
so `--check` passing is never mistaken for evidence having been re-verified.

**R-ARCH-013 · LOW (corroboration, not a new finding)**
Rubric: PART-05 — already filed as **R-RETR-005** this round (`ROUND_04/R-RETR.md`)
I independently reproduced the same gap before reading `R-RETR.md`: `Source._one_position_
holds_one_disposition` computes occupancy but never bounds a position against `stated_total`
(`MessageRow.position: int = Field(ge=0)`, no upper bound) — a single-row `Source
(stated_total=3, ...)` with `position=900` builds cleanly (`scratchpad/rarch4/
probe_position_range2.py`). HANDOFF §6 discloses this honestly as blocked on an unresolved
0-/1-based convention question; R-RETR-005 files the escalation. Filed here only so it is
not mistaken for something my probes turned up that HANDOFF hid.

## Hollow-implementation list (Priority 3 — degenerate-strategy probe)

| Mechanism | Dumbest implementation consistent with the tests | Caught? |
|---|---|---|
| Position occupancy (R-RETR-002) | Track a row/run occupancy dict, raise on any clash — with no bound relating a position to `stated_total` | Occupancy clashes: **caught** (verified — see Execution record). Out-of-range positions: **not caught** (R-RETR-005, corroborated above) |
| Sealed observations + endpoints (A2) | Single `_admit` writer, endpoint-checked intake dispatch, but any in-process caller can still construct a `FetchedIds(ids=[...], endpoint=...)` naming ids nothing fetched | Internal-discipline attacks (wrong-endpoint intake, bare list, shortlist inflation): **caught** — AST single-writer test + 3×3 endpoint matrix + hypothesis property over all three clauses at once, all independently re-run and confirmed. Fabricated-but-well-formed observations: **not caught by design**, honestly named as blocked on amendment A1 |
| Constant fold (R-SEC-013) | Fold exactly nine literal-adjacent call/operator shapes by pattern-matching the call node; never resolve a `Name` through an assignment | The nine named idioms: **caught** (reconfirmed each). A one-hop variable-fed split (`PART = "ground"`; `PART + "_truth/cases.json"`) defeats it completely — reconfirmed live: `python -m tools.guards` reports **0 violations, "guards clean"** on `scratchpad/rarch4/var_fed2.py`. Disclosed as the round's largest residual gap; still true |
| Alias scope tree (R-SEC-015) | Approximate control flow with "nearest binding above the call, in-scope; last binding wins across a scope boundary" | The two false positives Round 3 found: **caught** (reconfirmed: exactly 1 violation for 1 real write, not 2, on the verbatim two-function reproduction). Genuine control-flow cases (while-loop rebind, try/except, cross-scope closures called before a later rebind) are approximated and can go either way — HANDOFF discloses two of these; R-SEC's own Round 4 pass (`R-SEC-017`) found a third the disclosure didn't name |

## Execution record

```
uv run ruff check . / ruff format --check . / mypy          → clean (87 / 87 / 61 files)
uv run pytest -q -m "not network"                             → 406 passed
uv run python -m tools.guards                                 → clean, 6 sweeps
uv run python tools/rubric_status.py --check                  → 9 PASS / 104 NOT TESTED / 9 transitions
scratchpad/rarch4/run_defeats.py                               → 7/9 structural attacks caught, table above
scratchpad/rarch4/probe_position_range2.py                     → position=900 in stated_total=3 builds (R-RETR-005 corroborated)
scratchpad/rarch4/var_fed2.py + guards                         → variable-fed fold bypass reconfirmed live, 0 violations
Defect reintroduction (R-RETR-002): deleted `_one_position_holds_one_disposition` in an
  isolated /tmp copy (fresh `uv sync`, isolated UV_CACHE_DIR — a copied .venv silently
  re-resolves imports back to /root/mailweave and gives false negatives; noted so a later
  reviewer doesn't lose time to the same trap) → exactly 5 tests fail, matching HANDOFF's
  claimed "+4 more" exactly (the same-slot test plus partial-overlap, row-vs-run, the
  ledger-backed end-to-end test, and the hypothesis property).
A2 architecture fidelity: `docs/ARCHITECTURE_DECISION.md:406` (H-thr clause) cross-read
  against `docs/ARCHITECTURE_AMENDMENTS.md`'s A2 text and `disposition.py`'s `_admit`/
  `record_thread` — single-writer property, endpoint-checked intake, and "not closed here"
  residual all match the amendment's own "explicitly not changed" clause verbatim.
No project source or test file in /root/mailweave was modified at any point.
```

## Per-criterion recommendations

| Criterion | Recommendation | Basis |
|---|---|---|
| PART-02, PART-03, ROUTE-01, NFR-01, NFR-04, REG-04, SEC-04 | **PASS stands** | Clean match between ledger evidence and the cited report's own recommendation |
| INJ-04 | **Re-cite or re-verify, do not revert** | R-ARCH-009: claim likely true across three rounds' evidence, but the ledger row as written doesn't establish it |
| PART-07 | **Re-cite or re-verify, do not revert** | R-ARCH-010: promoting reviewer explicitly withheld the coverage half; unaddressed for three rounds |
| R-RETR-002, A2 | **Gating criteria — CLOSED**, corroborating R-RETR's verdict | AST test, 3×3 matrix, two hypothesis properties, my own defect-reintroduction all confirm; R-RETR-005 is the honest residual |
| SEC-01/03/05/08 guard findings | Defer to `R-SEC.md` (this round) | Consistent with my spot-checks of `_is_write_shape`, `_Scope`, the fold |
