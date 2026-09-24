# R-ARCH — Round 9

**Reviewer:** R-ARCH (fresh instance, `AGENT_LOOP.md` §3). Did not write this code.
**Scope:** `docs/reviews/ROUND_09/WORK_ORDER.md`, gating reviewer for A7 and the fifth corpus.
**Method:** execution only (§4/§7). `.venv`/`.pytest_cache`/`.mypy_cache`/`.ruff_cache`/
`.hypothesis` wiped, `uv sync --all-packages --extra dev` re-run before any measurement;
`mailweave.__file__` confirmed as `server/src/mailweave/__init__.py` — the real tree, not a
stale install. Destructive experiments ran against copies in `/tmp/mailweave-review` and
`/tmp/mailweave-attack`; nothing in `/root/mailweave` outside this file was touched.

**Verdict, up front:** containment cannot be defeated through any reachable path. Zero
BLOCKER, zero HIGH. Four MEDIUM/LOW findings, all about default-view quality and
reviewability — none release-blocking under this round's own rule that default-view quality
is reported, not gated. **Round 9 should gate** on the criteria it targeted.

## 1. Attacking containment

`AnnotatedBody.__post_init__`'s tiling check was attacked on every route named plus several
not named. Every attempt through the type's real constructor was refused.

| route | result |
|---|---|
| overlap, zero-length span, out-of-order, a gap, duplicate spans over one range | refused, `AnnotationContainmentError`, correct diagnostic each time |
| NFD combining chars, ZWJ emoji, bidi overrides, NFKC-foldable ligatures, via real `annotate_body` | **held**, reconstructed exactly |
| astral chars, lone/unpaired surrogates mid-string | **held** |
| empty body, whitespace-only body | **held** |
| `build_annotation` given a wrong-length classification list | refused |
| `str` subclass with `__eq__` always `True`, to spoof the rejoin check | refused — contiguity check runs independently and catches it first |
| 5,000-example Hypothesis run, full `0x0`-`0x10FFFF` (wider than the suite's 400/400, incl. lone surrogates) | **held**, 0 failures |
| reintroducing deletion in `build_annotation` (skip non-`ORIGINAL` spans — round 8's operation) | fails hard at construction: `339 failed, 829 passed`, exactly the claimed count |

**One caveat, LOW, not exploitable via any path in this repo.** `object.__setattr__` on a
built `AnnotatedBody`, a raw `object.__new__` skipping `__init__`, and a forged
`pickle.loads`/`__reduce__` all build a containment-violating instance, because none calls
`__post_init__`. This is general to *any* Python dataclass (same caveat applies to
`Envelope`), and nothing in `mailweave` does this. **R-ARCH-027** — the docstring's
"no way to build... no path that skips the check" should say "no path through this module's
public API," not imply physical impossibility.

**The gate holds** — a property of the type, verified live by breaking it and watching the
break get refused.

## 2. Fifth corpus: destruction vs. default-view misclassification

32 new entries (≥25 required), none copied from any fixture; both positions reimplemented
independently rather than imported — 64 entry/position pairs. Script:
`<scratchpad>/fifth_corpus.py`, not committed to the tree.

**Destruction: 0/64**, by both text-identity and rejoin checks, independent of the shipped
assertions — the gate holds on a corpus built to attack it.

**Default-view misclassification — four shapes, one known, three new:**

| shape | pairs | recoverable one class wider? |
|---|---|---|
| `Bcc:`/`Reply-To:` header-field prose (R-ARCH-025's mechanism, 2 fields it never tried — `_QUOTE_HEADER_LINE_RE` at `quotes.py:482` matches 8 names, R-ARCH-025 used 6) | 3×2 | **no** — `QUOTED` |
| sign-off word alone, then real content ≤60 chars (`Best,`/`Thanks,`/`Cheers,`/`Sincerely,`/`Regards,`) | 5×2 | **no** — `SIGNATURE`. `_MAX_SIGNATURE_LINE_CHARS=60` (`quotes.py:512`) is a hard line: a 61-char continuation survived, a 60-char one did not |
| forward separator or header block earlier in a message, sender's inline reply between `>`-quoted paragraphs *later* | 3×2 | **yes** — `UNCERTAIN`, but contradicts `classify_lines`'s own docstring (`quotes.py:882`: "an inline reply... keeps every answer") once anything besides the `>` chain exists anywhere in the body |
| a lone `>`-line used as punctuation/callout, not a real quote | 2×2 | **no** — `QUOTED` |

Zero false positives on: new Danish/Norwegian/Finnish prose, CJK, combining diacritics,
emoji, three divider styles (`----`/`***`/`========`), five more attribution-shaped-but-
unrecognised sentences, and two entries built to be genuine attribution lines (hyphenated
name, role-account address) — all correct.

**Rate:** entry-level (any fragment hidden, matching the shipped test's own counting),
**32/64 = 50.0%** — a corpus built to hit under-tested signals (`Bcc`/`Reply-To`, the
sign-off detector) beats the reported 5.5% by 9x. Not a contradiction of that number, but
evidence it is corpus-specific, not a ceiling. **R-ARCH-028**, MEDIUM, not gate-blocking
(default-view quality is reported, not gated, this round).

**"Recoverable one class wider"?** Checked directly: **not as a blanket claim.**
Re-running `R_ARCH_ROUND_8_PROSE` against `ONE_WIDENING=(ORIGINAL,UNCERTAIN)`: all 14
misclassified entries still miss ≥1 fragment (8 are `QUOTED`; 6 have a `FORWARDED` heading
line, though the sentence beneath it recovers). `HANDOFF.md` itself is precise — it only
claims the 7 *collateral neighbour* paragraphs and `LATCH_CORPUS` are one-widening-
recoverable, never the 14 sentences. But the weaker general framing this review was asked to
check does not hold. **R-ARCH-029**, LOW — the real basis for downgrading from BLOCKER is
containment (full text always in `body_clean.text`), not "one widening always suffices";
state the recovery guarantee as `view(list(SpanClass))`, not "one class wider."

**Byte-identical-to-round-8 claim:** **not independently reproducible.** Round 8's
`quotes.py`/`_segment` exists nowhere in the tree, there is no `.git`, and `docs/archive/`
holds only the pre-round-1 doc. The **293-body count is verified** (254+23+16=293, by direct
count of today's fixtures). The character-level comparison itself cannot be re-run because
round 8's code is gone; the downstream numbers it supports (0/254, 14/254, 1,264/1,264) *are*
independently verified via the live, executable test suite. **R-ARCH-030**, MEDIUM — a claim
central to "no quality snuck into a refactor" rests on a discarded script; archive round 8's
`quotes.py` or the comparison script so the claim stays checkable (§7.1).

## 3. The latch

Both halves verified by executing (not reading) `test_the_latch_no_longer_destroys_...` and
`test_the_latch_still_gets_the_default_view_wrong_...`, both green.

- **Destruction: 1,264/1,264 → 0/1,264.** Confirmed.
- **Default view: still 0/1,264 shown**, `shown_widened == tagged` (1,264/1,264 recovered by
  `ONE_WIDENING`) **for `LATCH_CORPUS` as built** — every tagged character sits strictly
  inside an unmarked extent, no marker interleaved. §2's forward-then-inline-reply shape is
  the same mechanism under different geometry and is also fully recoverable — the good case.
  §2's header-block/sign-off shapes are not latch-driven at all — the structural line itself
  is misclassified, which `ONE_WIDENING` was never built to reach. **The latch dissolves
  exactly as claimed; "one class wider" does not generalise past it.**

## 4. Scope discipline and the left-open items

No `.git` in this checkout, so scope was checked against `HANDOFF.md`'s file list and
content rather than a diff. `envelope/disposition.py` (not in HANDOFF's "what was built"
table) is where `_sealed_scalar`/`_sealed_numeric_id`/`_sealed_id` live — in scope for Part
2, just omitted from the summary table. No file outside A7's consumers or the seal was
touched. S-1 (`next_page_token`, the one disclosed out-of-scope fix) is honestly justified:
the fourth unbounded field in the exact object R-SEC-031 names.

**S-2..S-5, all reproduced exactly, genuinely left (no partial fix):**

```
S-2: strip_invisible_characters("Pay ­now" + <6 tag-block chars>) -> removed_chars=0,
     tag characters survive. U+061C (Arabic Letter Mark) also survives.
S-3: HistoryAddition(history_id="Please review the attached NDA before end of day.").render()
     -> 'history.list messagesAdded since historyId Please review the attached NDA before end of day.'
S-4: auth/tokenstore.py:55  obtained_at: str = Field(min_length=1), never parsed — present, unchanged.
S-5: '²'.isdigit() -> True ; int('²') -> ValueError, uncaught in sweep_orphaned_temporaries
     (only unlink() is try/except'd), contradicting its docstring "every error is swallowed."
```

## 5. Findings

```
ID:            R-ARCH-027
Severity:      LOW
Rubric:        none — documentation precision
Location:      server/src/mailweave/content/annotate.py:131-145
Reproduction:  object.__new__(AnnotatedBody)+object.__setattr__, or a forged pickle
               __reduce__, builds a containment-violating instance without __post_init__
Expected:      the "unrepresentable" claim scoped to this module's public API
Actual:        phrased as absolute; reflection defeats it (true of every dataclass here)
Required fix:  reword the docstring; no code change needed
```

```
ID:            R-ARCH-028
Severity:      MEDIUM
Rubric:        none — reported metric, not gated (WORK_ORDER.md Part 1)
Location:      quotes.py:482-484 (_QUOTE_HEADER_LINE_RE), :496-512 (_SIGN_OFF_RE)
Reproduction:  fifth_corpus.py — 32 entries/64 pairs, 0 destroyed, 32/64=50.0% missing from
               default view (Bcc/Reply-To prose, sign-off-then-content, lone '>')
Expected:      the reported miss rate (5.5%) reflects the weakest signals measured
Actual:        it is specific to the four existing corpora; an adversarial one finds 50.0%
Required fix:  none this round; log for the next default-view-quality round with R-ARCH-025
```

```
ID:            R-ARCH-029
Severity:      LOW
Rubric:        none — documentation clarity
Location:      HANDOFF.md (R-ARCH-026 section); test_a7_default_view_quality.py ONE_WIDENING
Reproduction:  R_ARCH_ROUND_8_PROSE vs view(ONE_WIDENING): all 14 entries still miss ≥1
               fragment (8 QUOTED, 6 have a FORWARDED heading line) — §2
Expected:      "recoverable one class wider" scoped to what it is true of
Actual:        HANDOFF scopes it correctly (7 neighbours, LATCH_CORPUS); the general framing
               this review checked is not true beyond those two cases
Required fix:  state the recovery guarantee as view(list(SpanClass)), not "one class wider"
```

```
ID:            R-ARCH-030
Severity:      MEDIUM
Rubric:        none — process/reviewability (AGENT_LOOP.md §7.1)
Location:      HANDOFF.md, "No tuning happened" section
Reproduction:  round 8's quotes.py/_segment is absent from the tree; no .git; docs/archive/
               holds only the pre-round-1 doc. 293-body count verified (254+23+16=293)
Expected:      a claim central to "no quality snuck into a refactor" stays checkable
Actual:        the comparison script and round 8's code are both gone; downstream numbers
               it supports are independently verified via the live suite, this comparison isn't
Required fix:  archive round 8's quotes.py or the comparison script under docs/archive/
```

## 6. Execution record

```
rm -rf .venv .pytest_cache .mypy_cache .ruff_cache .hypothesis && uv sync --all-packages --extra dev
python -c "import mailweave; print(mailweave.__file__)"
  -> /root/mailweave/server/src/mailweave/__init__.py   (real tree, confirmed)

uv run ruff check .              -> All checks passed!
uv run ruff format --check .     -> 95 files already formatted
uv run mypy                      -> Success: no issues found in 69 source files
uv run pytest -m "not network"   -> 1168 passed in 13.73s
uv run python -m tools.guards    -> guards clean (7 guards)

Reintroducing deletion in build_annotation (scratch copy /tmp/mailweave-review):
  -> 339 failed, 829 passed   (claimed 339 failed — confirmed exactly)

5,000-example Hypothesis run, full 0x0-0x10FFFF incl. lone surrogates, via annotate_body:
  0 failures.

Direct repro of S-2, S-3, S-4, S-5 (§4): all four match HANDOFF's text exactly.

Fifth corpus (32 entries, 64 pairs, independent position reimplementation):
  destroyed 0/64; default-view misses 32/64 (50.0%).
```

No rubric row, ledger row, or transition was written by this review, per the work order.

## 7. Per-criterion recommendation

| criterion / property | this round's claim | verdict |
|---|---|---|
| Content containment (A7's gate) | no input character absent from output | **holds** — every attack refused; reintroduced deletion fails loud |
| Default-view quality | reported, not gated | **reported honestly**; 5.5% understates the miss rate on under-tested signals (50.0% on an adversarial corpus) — schedule R-ARCH-025-class work, informed by R-ARCH-028 |
| R-ARCH-026 (the latch) | dissolves as destruction, persists as a view defect | **confirmed, both halves**; "one widening" recovers the latch specifically, not every default-view defect (R-ARCH-029) |
| Scope discipline | no adjacent improvements riding along | **held**; S-1 disclosed and justified; S-2..S-5 genuinely left, all reproduced |
| DISC-03 (depth vocabulary / declared reductions) | not claimed PASS this round | correctly `NOT TESTED` — `body_clean` has no consumer in `envelope/` yet |

**Gate recommendation: PASS this round on the criteria it targeted.** Zero BLOCKER, zero
HIGH. The findings above are MEDIUM/LOW, address reporting precision and future work, and
none is gated by this round's own rules.
