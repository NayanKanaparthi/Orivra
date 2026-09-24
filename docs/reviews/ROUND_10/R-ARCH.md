# ROUND 10 — R-ARCH review

**Reviewer:** R-ARCH, independent instance, 2026-08-31. Verified by execution per
`AGENT_LOOP.md` §4/§7. Added because the diff grew past `WORK_ORDER.md`'s four parts
(Part 1's ten-field sweep). `.venv`/caches wiped, resynced; `mailweave.__file__` →
`/root/mailweave/server/src/mailweave/__init__.py`. Source/tests not modified in place;
mutation happened on a full copy in `/tmp/mailweave-review/repo`, itself resynced.

## Priority 1 — harness-residue verification (checked first)

**Method.** No git in this container, so "clean" was established by reading, not
diffing: (a) every field the handoff claims was touched, read end-to-end; (b) file
mtimes ordered chronologically, to check nothing was edited after `HANDOFF.md` was
written; (c) my own reintroduction harness in `/tmp`, never reading theirs (it isn't in
the tree — a scratch tool, not a deliverable).

**Reading.** `reasons.py`: all ten string parameters use `ReasonScalar` or
`GmailNumericId`, none left as bare `Field(min_length=1)` — the shape a stuck restore
would leave, since defect **B** edits exactly these ten annotations in one file.
`constants.py`, `disposition.py`, `transport.py`, `tokenstore.py`, `html_text.py`: each
matches its described change, nothing half-applied. `wire.py`'s unchecked
`why`/`q`/`method`/`model`/`basis` fields match the handoff's "found and deliberately
left" list verbatim — expected, not residue.

**Chronology.** File mtimes run `reasons.py → constants.py → tokenstore.py →
html_text.py → annotate.py/pipeline.py → quotes.py → test_wire_retention_round10.py →
transport.py → test_a7_default_view_quality.py → ROUND_10/HANDOFF.md`, strictly
increasing, nothing after the handoff except this session's own pytest-cache
regeneration. `wire.py`'s mtime predates the whole cluster — untouched, as claimed.

**Independent reintroduction.** Copied the repo to `/tmp/mailweave-review/repo`,
resynced (`mailweave.__file__` confirmed local), baseline 1,529 passed. Per defect:
patched with `sed`/Python, ran `pytest -m "not network"`, restored, `diff`-verified
empty against both the pre-edit copy and the real tree.

| defect | my result | handoff row | match |
|---|---|---|---|
| A — `history_id` back to the one-line floor | **15 failed**, 1,514 passed | 15f, 1,508p | failure count exact |
| B — all ten reason params back to `Field(min_length=1)` | **25 failed**, 1,504 passed | 25f, 1,498p | failure count exact |
| D — 16-code-point hand-list restored | **11 failed**, 1,518 passed | 11f, 1,512p | failure count exact |
| G — transport seam `start_history_id` unchecked | **5 failed**, 1,524 passed | 5f, 1,524p | **exact, both cols** |
| C — `^`/`$` instead of `\A`/`\Z` | **2 failed**, 1,527 passed | 1f, 1,522p | off by one, below |

Four of five reproduce the reported failure count exactly; G matches both columns. The
"passed" totals are not noise: rows A/B/C/D/F all sum to 1,523; E sums to 1,522; G and H
sum to 1,529 (today's full total) — the suite grew from the round-9 baseline of 1,168 as
work proceeded, and rows were captured incrementally, not all re-run against the final
tree. Row C is the one place this bites: on the final tree **two** tests now exercise
the shared pattern's anchoring (`reasons.py`'s near-miss case, and `transport.py`'s —
row G's own test, added later), where only the first existed when C was captured.
Restoring the anchor makes both pass again — confirmed: a measurement-timing artifact,
not a wrong count, corroborated by three other rows landing on the same two totals.

**Verdict: the tree is clean.** No half-applied field, no post-handoff edit, and the one
count that didn't reproduce verbatim is explained and cross-checked. `make check` on the
real tree: `ruff check` clean, `ruff format --check` 97 files, `mypy --strict` 71 files
clean, `pytest -q -m "not network"` **1,529 passed**, `tools.guards` 7 clean,
`rubric_status.py --check` 7 PASS / 106 NOT TESTED / 11 transitions — matches handoff
and R-SEC.

## Priority 2 — the scope expansion, as architecture

**The shared constant (`GMAIL_NUMERIC_ID_RE`) is the right structure**, because it
encodes an objective fact about an external system, not a policy choice: whether a
Gmail `historyId` is "≤20 ASCII decimal digits" is not something three layers are
entitled to disagree about — disagreement there is the bug, which is exactly how
R-SEC-030/032 recurred (independently *written* copies of one fact). Centralizing it in
`constants.py` — already home to other externally-sourced shapes (`GMAIL_ENDPOINTS`, the
egress allowlist) — with three importers and reflection tests walking `get_args(Reason)`
rather than listing kinds, is correct. **This part breaks the cycle.**

**The single-line floor does not, and the evidence is in the same file.**
`disposition.py` already has `_is_one_line(value) -> bool: return value.splitlines() ==
[value]`, from R-SEC-029 (round 9). `reasons.py`'s new `_one_line` — written this round,
in the commit that argues against rewriting the numeric-id shape — is `if
value.splitlines() != [value]: raise ...`: the same primitive, independently
reimplemented. Both correct today, so no test catches the duplication (tests check
behavior, not provenance). It is a live instance, in round 10, of the pattern round 10's
own Part 1 diagnosis describes. (Not identical *policies* — the seal also bounds length
at 64 chars, reasons.py deliberately doesn't — so full collapse would be wrong; but the
boundary-detection primitive has no reason to exist twice, and a shared `_is_one_line`
would preserve the differing length policy while removing the duplicate mechanism.)

**`auth → envelope.wire` is a real cost, larger than disclosed.** The handoff calls it
"one layering consequence." Measured: importing `mailweave.auth.tokenstore` now
transitively pulls in all of `mailweave.envelope` (builder, disposition, fence, measure,
reasons, response, vocab, wire) **and** all of `mailweave.content` — the whole
disclosure/content stack, versus only `constants`+`errors` before. Cost:
`envelope.wire` alone is **+0.155s** import time over `constants`+`errors` (0.166s vs
0.011s, measured), now paid by every process that touches credentials. No cycle, guards
clean, R-SEC independently confirmed the direction — but "no cycle" is a low bar for a
credential store that was two stdlib-adjacent modules deep and is now importing a
disclosure-layer package graph. The handoff's own suggested alternative — move
`parse_instant` below both `auth` and `envelope` — is the better fix and belongs in a
follow-up, not as a standing trade-off.

**Net ruling: partial break.** The numeric-id shape is now genuinely single-sourced
across three real layers — correct use of one shared constant for one objective
external fact. The single-line-floor *mechanism* gained a second independent copy in
the same round that diagnosed copies as the problem, and the sweep's fix was paid for
with a coupling cost between a previously-isolated module and the entire content/
envelope stack. Progress — one real shape now provably single-sourced, gaps named
rather than hidden — but not closure of the underlying cycle.

## Priority 3 — test quality, 1,168 → 1,529

**The 272 (not 273 — confirmed via `pytest --collect-only`, matches R-SEC-038) code-
point-walking cases partition the space**, not one assertion repeated: each case covers
a disjoint 4,096-code-point slice of `U+0000..U+10FFFF`, together exhaustive over every
non-`Cf` code point. Real assurance against a widened stripper eating visible text.

**Tried to defeat the `Cf` set-equality test.** Replaced `invisible_character_patterns()`
with a hand-transcribed, hardcoded partition of today's 170 `Cf` code points (baked from
`unicodedata` once, not derived at runtime): **all 298 cases in the file pass**, full
suite stays at 1,529. **The test does not distinguish "derived" from "correctly and
completely transcribed."** It verifies exactness for *this* Unicode version — which a
stale hand-list (round 9's 16 entries) cannot satisfy, the real defect — but "a
hand-list cannot pass" (the module's docstring) isn't quite true for a complete one.
What derivation buys — the 171st `Cf` character for free — isn't exercisable by any test
on this interpreter, only argued. R-SEC's report reaches the same conclusion; I verified
it by execution rather than argument.

**Spot-checked non-parametrized tests.** `test_wire_retention_round10.py` pairs every
negative with a positive case, asserts refusal messages name the offending field, and
drives probes through `MessageRow.model_validate` as well as constructors. `test_a7_
default_view_quality.py`'s one addition recomputes the (14, 14) figure and the 8/6
span-class breakdown from the corpus live, not a hardcoded literal. Nothing
spot-checked was tautological.

## Priority 4 — degenerate-strategy probe

| mechanism | dumbest implementation consistent with tests | caught? |
|---|---|---|
| shared `GMAIL_NUMERIC_ID_RE` | 3 duplicated (currently identical) regex literals, no import | **No** — behavioral tests only; verified true only by reading source. |
| derived `Cf` set | hardcoded 170-entry transcription, baked once | **No** — proven by execution (298/298 pass); catches stale lists, not complete-but-static ones. |
| ten-field single-line floor | revert `_one_line` to round-8's `"\n" in value or "\r" in value` | **Yes** — `TWO_SENTENCES` embeds a literal U+2028 to defeat exactly this scan. |
| `obtained_at` via `parse_instant` | local reimplementation, not importing `envelope.wire` | **No** — behaviorally identical, no identity/import test. |

Three of four mechanisms' strongest architectural claim (single source, derivation,
shared import) rests on reading, not on a test that could fail — provenance generally
isn't test-observable, but it means a future silent regression (pasting a copy instead
of importing) would sail through undetected.

## Findings

```
ID: R-ARCH-031  Severity: LOW  Rubric: none — architecture/maintainability
Location: envelope/reasons.py:70-76 (_one_line); envelope/disposition.py:189-206 (_is_one_line)
Repro: read both; splitlines() != [value] and splitlines() == [value] are the same
  primitive negated, written independently in the same round.
Expected: the round's own rule ("two separately written copies of one shape is how the
  second layer went unchecked") applied to itself.
Actual: a second copy exists, undetected because both are correct today and no test
  checks provenance.
Required fix: factor the boundary check (not the length policy, which differs by
  design) into one shared helper both call.
```
```
ID: R-ARCH-032  Severity: LOW  Rubric: none — coupling, adjacent to R-SEC's "layering consequence" note
Location: auth/tokenstore.py:24 (import mailweave.envelope.wire)
Repro: importing mailweave.auth.tokenstore before/after — auth/* previously imported
  only constants+errors; now transitively imports all of envelope/ and content/.
  envelope.wire alone costs +0.155s import time over constants+errors (measured).
Expected: the credential store's dependency footprint stays proportional to what it does.
Actual: the whole disclosure/content package graph is now reachable from every process
  touching credentials.
Required fix: move parse_instant below both auth/ and envelope/, per the handoff's own
  suggested alternative, rather than carry the import as a standing trade-off.
```

Both LOW, neither blocks. R-SEC's R-SEC-036/037/038 are in their report; I independently
matched the 272 count and 19-not-18 `bidi_override` delta before reading it.

## Execution record

Full `make check` on the real tree (all green, matching handoff). Independent
reintroduction harness in `/tmp/mailweave-review/repo` (separate resync) for defects
A, B, C, D, G — patched, tested, restored, `diff`-verified against both the pre-edit
copy and the real tree. Degenerate-implementation probes for the `Cf` set (298/298
passed) and the numeric-id constant (read-only). Independent bucket recount for
`bidi_override` (31, minus `Bidi_Control`'s 12 = 19 extra).

## Recommendations, per criterion

- **Three-layer numeric-id sweep**: sound structure, correctly centralized, endorsed.
- **Ten-field single-line floor**: correctly scoped, well-tested against its own known
  regression class (U+2028) — but a second hand-written copy of an existing primitive.
  R-ARCH-031, LOW, no block.
- **`auth → envelope.wire`**: works, guards clean, footprint larger than disclosed.
  R-ARCH-032, LOW, no block; worth fixing before WS-02 adds more weight to `auth/`.
- **INJ-04 hidden-character clause**: architecture evidence sound; the suite's proof of
  "derivation" is weaker than its docstring claims (matches R-SEC) — doesn't change the
  PASS call, which is R-SEC's to make.
- **Test growth (1,168 → 1,529)**: not inflation. Parametrized cases partition real
  space; non-parametrized additions pair positive/negative and measure rather than
  assert literals. No hollow test found in the sample checked.
- **Gate**: nothing here rises to HIGH or BLOCKER. Round 10 does not need to fail on
  architecture grounds; the four open LOW/MEDIUM findings (R-SEC's three, mine two)
  should be recorded, not silently dropped, per `AGENT_LOOP.md` §9.
