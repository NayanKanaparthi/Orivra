# ROUND 10 — R-SEC review

**Reviewer:** R-SEC, independent instance, 2026-08-31. Verified by execution per
`AGENT_LOOP.md` §4/§7. `.venv`/caches wiped, `uv sync --all-packages --extra dev`,
`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`. Source/tests
not modified; probes ran in `/tmp/rsec_probes/`.

## Environment

`ruff check` clean. `ruff format --check` 97 files. `mypy` strict, 71 files clean.
`pytest -q -m "not network"` **1,529 passed** (matches handoff; 1,529 − 1,168 round-9
baseline = 361 new, matching 62+298+1). `tools.guards` 7 clean. `rubric_status.py --check`:
7 PASS / 106 NOT TESTED / 11 transitions, unchanged.

## Part 1 — R-SEC-032 and the sweep: VERIFIED, one overclaim found

All three layers checked live: seal (`disposition._sealed_numeric_id`), `reasons.py`
(`HistoryAddition.history_id`), `transport.py` (`list_history_additions`). Each refuses
the reviewer's original sentence and `"99120034\n"`. `constants.GMAIL_NUMERIC_ID_RE` is
`\A[0-9]{1,20}\Z`, one definition, three importers (grep-confirmed); independently compiled
`^…$` vs `\A…\Z` against the trailing-newline value — old matches, new doesn't, as claimed.
The full round-9 wire reproduction re-run: refused with `pydantic.ValidationError`.

**Sweep to ten fields:** confirmed in `reasons.py` — nine carry `ReasonScalar`
(`_one_line`), one carries `GmailNumericId`. All ten refuse a three-line body (reflection
test walks `get_args(Reason)`, not a fixed list; spot-executed).

**Scope-expansion ruling: right call.** Leaving nine reproducible instances of R-SEC-032's
exact defect in the file being fixed would repeat last round's §1.3 shape exactly. The
diff is small and self-contained; endorsed.

**Single-line floor, sufficiency:** not sufficient by itself, and already honestly
disclosed as such. Built a 1,130-character single-line "sentence" (deal-team
confidentiality language, no breaks) — accepted as a `query`, reaches the wire. `_one_line`
closes the multi-line channel only; no field needs *more* than single-line by nature, but a
length bound is still missing project-wide. Matches the handoff's own "narrowed, not
closed."

**New finding from sweeping further:** the handoff claims `MessageRow.id`/`Source.thread_id`
are "closed transitively, by an invariant" refusing an id/thread the ledger never observed.
**False, verified by execution** — I built a `Source`/`MessageRow` (real production types,
no test hook) whose `thread_id` and `id` were each a full sentence never observed by any
rung; it built and serialized cleanly, both sentences on the wire. The invariant's own
docstring names this exact case: *"the id is not in `H` at all — the ledger has no
opinion."* Traced to round 7's field census, which already classifies this as **A1's
residue** — pre-existing, documented, and A1 is explicitly out of scope this round. So: not
a new hole, but the round-10 handoff mischaracterizes it as closed. Filed as R-SEC-036,
MEDIUM (see below).

**`wire.py`'s `why`/`q` (the implementer's own "fourth layer"):** confirmed real
(`Field(min_length=1)`, no shape check) and honestly described. `note_withheld` has zero
call sites in `server/src` (only tests) — no Gmail client exists to populate `why` yet, so
"no route from mail content today" checks out. Leaving these is reasonable; it is a fourth
layer and needs a per-field decision this round correctly declines to invent.

**Verdict:** R-SEC-032 fixed; sweep correctly scoped and executed. One MEDIUM
documentation-accuracy finding; does not block.

## Part 2 — INJ-04, full scope

**Derivation genuinely verified**, independently: `unicodedata.category==Cf` gives 170
code points (Unicode 15.0.0, matches runtime). Ran the stripper on exactly those 170
characters: `removed_chars==170`, output empty. Reproduced the three-cause split
independently (`bidi_override` 31, `zero_width` 126, `invisible_format` 13) — matches.
All three named probes (U+061C, U+00AD, U+E0000-block "HIDDEN") now stripped and counted.
**One caveat on the "cannot pass" claim:** the set-equality test compares against
`unicodedata` computed live, so a hand-list that happened to enumerate today's exact 170
would also pass *today*; what a hand-list cannot do is stay correct across a Unicode-data
upgrade, which is the property that actually matters and matches R-SEC-029/035's shape.

**Per-clause evidence against `RELEASE_RUBRIC.md`'s INJ-04 text:**
1. *Maintained parser → visible text* — unchanged, `test_content_pipeline.py`/
   `test_content_units.py` still green, untouched by this diff.
2. *Hidden constructs removed + declared* (this round's subject) — verified exhaustively
   both directions: all 170 `Cf` removed and counted; 272 chunks covering every non-`Cf`
   code point in `U+0000..U+10FFFF` remove zero characters. Every removal attributed to a
   counted `Reduction` (DISC-03).
3. *Zero network* — unchanged, still enforced by `conftest.py`'s socket block; reran and
   confirmed.

**Recommendation: PASS the hidden-character clause**, on this evidence, covering all three
parts for the characters in scope. **Not** a recommendation to mark the whole INJ-04
criterion PASS — the parser and non-character hiding mechanisms were not this round's
subject and are covered by unchanged tests only; marking the full criterion from this
evidence alone would repeat the exact narrow-citation mistake that reverted it twice.

**Ruling on the blanket `Cf` strip:** precise (only-and-exactly `Cf`, exhaustively
verified) and irreversible at every disclosure depth — it runs at extraction time, before
view/depth selection, so a wrongly-stripped character is gone from `body_full` too, not
just the default view. What cannot be established here: whether removing the 154
newly-covered characters changes what real Arabic/Indic/Syriac mail *says*, versus only
its invisible formatting — "no glyph" is not the same claim as "no effect on meaning," and
this repo holds no corpus in these scripts. **Recommend:** ship as-is (fail-safe per
DISC-03 — every removal counted and declared, nothing silent, and the `_KEPT_
FORMAT_CHARACTERS` extension point exists and is tested empty-by-decision); do not block
the gate on it (no rubric criterion requires a non-Latin corpus today, and fabricating one
would violate REG-04's offline-fixture rule); but record the non-Latin-corpus question as a
named open condition on INJ-04's *general* future PASS, the same way R-DISC's two A7
conditions are recorded for WS-11, so WS-02's real mail does not rediscover it as a
surprise.

## Part 3 — remaining items

**`obtained_at`: VERIFIED fixed.** `parse_instant("obtained_at", value)` via
`@field_validator`, imported not restated. Sentence refused; real instant round-trips
through `save`/`load`. New `auth → envelope` import direction confirmed by grep; no cycle,
guards clean — a real, disclosed trade-off.

**Credential-store crash: original fixed, one new variant found.** `_is_ascii_decimal`
correctly refuses superscript/Arabic-Indic/fullwidth digit PIDs — reproduced all three
live. **But** it bounds character class, not length: a 40-digit all-ASCII-decimal filename
passes the guard, `int()` accepts it (arbitrary precision), and `_process_is_alive`'s
`os.kill(pid, 0)` then raises `OverflowError` (not `OSError`, so uncaught anywhere in the
chain). Reproduced live against a real `TokenStore`: `sweep_orphaned_temporaries()` crashes,
contradicting its own "every error is swallowed" docstring, re-affirmed but not achieved
this round. Filed as R-SEC-037, LOW (same threat model as R-SEC-035: requires a file
already inside the 0700 credential dir).

## Findings (schema per §4)

```
ID: R-SEC-036  Severity: MEDIUM  Rubric: none — accuracy of a Part-1 "found and left" claim
Location: docs/reviews/ROUND_10/HANDOFF.md "Found and deliberately left" §1;
  server/src/mailweave/envelope/wire.py (MessageRow.id, Source.thread_id)
Repro: MessageRow(id=<sentence>) inside Source(thread_id=<sentence>), neither observed by
  any ledger rung -> EnvelopeBuilder.build() succeeds; both sentences verbatim in
  model_dump_json().
Expected: "closed transitively, by an invariant" to be true, or stated as honestly as why/q.
Actual: unchecked for any id/thread never observed - unchanged since round 7 ("an id
  outside H is A1's residue"), correctly out of scope for A1, mischaracterized as closed.
Required fix: correct the claim's wording. No code change required this round.
```
```
ID: R-SEC-037  Severity: LOW  Rubric: none — SEC-04 adjacent, same class as R-SEC-035
Location: auth/tokenstore.py (sweep_orphaned_temporaries / _process_is_alive)
Repro: a 40-digit all-ASCII-decimal filename field crashes sweep_orphaned_temporaries with
  an uncaught OverflowError from os.kill via _process_is_alive.
Expected: "every error is swallowed" (docstring, re-affirmed this round).
Actual: still crashes; the isascii()+isdigit() guard does not bound length.
Required fix: widen _process_is_alive's except to include OverflowError, or bound digit-
  string length before conversion.
```
```
ID: R-SEC-038  Severity: LOW  Rubric: none — documentation accuracy
Location: content/html_text.py:58-64 comment; HANDOFF.md ("18 code points... fifteen
  Egyptian hieroglyph joiners"; "273 parametrized cases")
Repro: independently enumerated bidi_override bucket (31) minus declared 12-member
  Bidi_Control = 19, not 18 (hieroglyph-joiner run U+13430-U+1343F is 16 points, not 15).
  len(range(0, sys.maxunicode+1, 4096)) = 272 (confirmed via pytest --collect-only), not
  273.
Expected: stated numbers match execution.
Actual: both off by one; harmless (nothing hardcodes either number) but ironic given this
  round's own thesis about hand-counted claims drifting.
Required fix: correct the two comments/prose numbers.
```

## Execution record

`rm -rf .venv .mypy_cache .pytest_cache .ruff_cache .hypothesis && uv sync --all-packages
--extra dev`; `mailweave.__file__` check; `ruff check .`; `ruff format --check .`; `mypy`;
`pytest -q -m "not network"` (1,529 passed); `python -m tools.guards`; `python
tools/rubric_status.py --check`; targeted reruns of `test_content_pipeline.py`,
`test_content_units.py`. Ten-plus standalone probes against the live tree covering: all
three `history_id` layers and the trailing-newline case at each; the full R-SEC-032 wire
reproduction; all ten reason parameters' floor and its length gap; the `Cf`-derivation
set-equality and both-direction exhaustive checks (recomputed independently, not read off
the suite); the `bidi_override` bucket recount; the `obtained_at` fix; both credential-sweep
crash variants; and the `MessageRow.id`/`Source.thread_id` closure claim (confirmed false,
then traced to round 7's field census to establish it as pre-existing and A1-scoped, not
new).

## Recommendations, per criterion/finding

- **R-SEC-032**: closed, verified at all three layers.
- **The ten-field sweep**: endorsed, in scope, correctly executed. Single-line floor is
  narrowing, not closure, for all ten — already disclosed.
- **R-SEC-033 / INJ-04 hidden-character clause**: **PASS** on the Part 2 evidence. Do not
  mark the whole INJ-04 criterion PASS from this alone.
- **The `Cf` blanket strip**: ship as-is; do not block the gate; record the non-Latin-corpus
  question as a named open condition for WS-02/WS-11.
- **R-SEC-034 (`obtained_at`)**: closed, verified.
- **R-SEC-035 (original crash)**: closed. **R-SEC-037 (new variant)**: open, LOW, no block.
- **R-SEC-036** (id/thread_id overclaim): open, MEDIUM, no block; correct before close.
- **R-SEC-038** (off-by-one counts): open, LOW, no block.

**Gate recommendation: Parts 1–3 clear R-SEC's domain.** Zero open BLOCKER, zero open HIGH.
Three findings remain open (one MEDIUM, two LOW); none meets this round's own bar for
blocking, but none should be silently dropped either. Part 1's exit condition ("no mail
text on the wire by any route") holds for every route this round's scope covers; the one
route left genuinely open (`id`/`thread_id` outside `H`) is pre-existing, tied to Amendment
A1, and correctly out of this round's charter — the defect found here is in the round's own
paperwork describing it as closed, not in new mail text reaching the wire.
