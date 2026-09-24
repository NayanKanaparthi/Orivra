# R-ARCH — Round 8 verification

**Reviewer:** R-ARCH (fresh instance, did not write this code or `HANDOFF.md`). 2026-08-31. Method:
execution only (`AGENT_LOOP.md` §4/§7). Carried forward from round 7: both the implementer and I
measured zero false positives while the guarantee did not hold, because we measured the path we
built rather than the path the text travels. That lesson drove every corpus below.

**Setup.** `.venv`/caches wiped in `/tmp/mailweave-review/mailweave`; `uv sync --all-packages
--extra dev`; `mailweave.__file__` confirmed inside that tree before trusting any result.
`ruff check`/`ruff format --check`/`mypy` clean, `python -m tools.guards` clean (7 guards),
`pytest -m "not network"` → **823 passed**, matches HANDOFF exactly. `email_reply_parser` is
absent from `uv sync`'s install list and `import email_reply_parser` fails — genuinely removed,
not merely unused. Every file patched for a reintroduction was restored and diffed
byte-identical before the next edit.

## §1 — The latch, attacked first (Priority 1)

The implementer disclosed it: `forward_separator`, `header_block` and
`client_attribution_unmarked_block` all **latch to end of message**, and none of the three round-8
corpora place sender prose *below* one. I built five shapes that do — reply-below, forward with a
note at the bottom, interleaved reply, a signoff after a latch, and a combined forward+signoff —
then a 16-case measured corpus across all three latching signals in reply-below, signoff, and
interleaved positions (`/tmp/mailweave-review/latch/measure.py`).

**Result: 1,251/1,251 tagged sender-authored characters destroyed — 100%, in all 16 cases, in
every shape tried.** Two representative cases, run through the full pipeline
(`process_message`, not just the stripper) to confirm the destruction reaches `body_clean`:

```
Hi team,

-----Original Message-----
From: Priya Shah
Sent: Monday, August 24, 2026 9:02 AM
...
Thanks,
Dana

I reviewed this and I think we should push back on the price before signing anything.
```
→ `body_clean == "Hi team,"`. The sender's own decision — the one sentence in the message that
matters — is gone.

```
On Monday, August 24, 2026, Priya Shah <priya@example.com> wrote:
We should finalize the budget by end of week and circulate it to finance.

I agree with the timeline but I want to flag the marketing line item still looks too low.

Also, can we get legal's sign-off before we send this out on Thursday?
```
→ `body_clean == ""`. An unmarked attribution with an interleaved reply loses the entire reply,
not just the quoted paragraph.

**This is disclosed, not hidden** — `StripResult.latched` is `True` in all 16 cases, and
`pipeline._removal_detail` writes "the removal ran to the end of the message because the client
marked no end … rather than a boundary the client wrote" into the `Reduction.detail` a caller can
read. That is real and distinguishes this from round 7's silent BLOCKER. But `body_clean` itself —
the primary representation — does not contain the sentence, `ambiguous_lines` is 0 in all 16 cases
(the ambiguity mechanism only inspects the line *directly above* a removal, never prose several
paragraphs below a latch start), and no production Gmail retrieval exists yet this round to
exercise the `unabridged`/`body_full` affordance the wire model reserves for this. Disclosed
content destruction is still content destruction. **Filed R-ARCH-026, HIGH** (§4).

## §2 — Layering verification (Priority 2)

Dependency genuinely gone: absent from `uv sync`'s install list, `import email_reply_parser`
fails, absent from `pyproject.toml`/`uv.lock`/mypy overrides. `IMPLEMENTATION_PLAN.md` WS-07 still
names it, as HANDOFF admits — orchestrator's item, confirmed unfixed.

No bypass: `strip_quotes_and_signature` is called from exactly one site
(`content/pipeline.py:258`), which is the only writer of `body_clean`. `strip_quotes_and_signature`
itself asserts every non-kept line carries a signal in `STRONG_STRUCTURAL_SIGNALS` before
returning (`quotes.py:1016-1025`) — verified this is live, not decorative, by deleting a signal
name from the dict and confirming the `AssertionError` fires.

**Reintroduction counts, reproduced exactly by running them**, restoring `quotes.py` between each:

| Reintroduction | Claimed | Reproduced |
|---|---|---|
| `_HEADER_BLOCK_MIN_FIELDS = 1` | 6 | **6** ✓ |
| `_SIGNATURE_DELIMITER_LINE_RE` back to prefix `(--\|__\|-\w)` | 4 | **4** ✓ |
| `On.*wrote:$` accepted at the `_segment` deletion call site | 17 | **17** ✓ (first attempt via `_client_attribution_template` itself gave 18 — the extra failure was `test_the_template_recogniser_names_the_format_it_matched`, a classification-only caller of that function; scoping the reintroduction to the actual deletion call site, as the claim implies, gives exactly 17) |

Round 7 BLOCKER reproduction — *"Once the negotiations concluded, the legal team wrote:"* —
**survives whole**, `quoted_chars=0`, confirmed both directly and through `process_message`.

## §3 — A fourth corpus, and a new false-positive class (Priority 3)

`R_ARCH_ROUND_7_PROSE` recount: **35 distinct entries**, not 36 (8+5+5+5+6+6). Confirmed
independently by counting the tuple — this is a real gap in *my own* round 7 report, not an
implementer fabrication; the implementer's transcription and disclosure are correct.

`PROSE_CORPORA` sizes confirmed: `implementer_round_7`=36, `r_arch_round_7`=35,
`implementer_round_8`=29 → 100 sentences × 2 positions = 200 pairs, all **0/200** — reproduced by
running `test_the_false_positive_rate_is_zero_for_every_corpus_in_every_position`.

**My fourth corpus** (27 sentences, `/tmp/mailweave-review/latch/r_arch_round8_corpus.py`) targets
the nearest untested neighbour of the fix: the three existing corpora each test **one**
header-field-shaped line per entry (correctly surviving, since `header_block` needs ≥2 distinct
fields). None tests **two consecutive** field-shaped lines arising from ordinary prose, or a bare
"Original Message"/"Forwarded Message" section label with no dashes — both are things a person
recapping a decision in memo style plausibly writes.

**Result: 14/54 = 25.9%** — worse than the round-7 tree's own 25/200 = 12.5% on the gated corpora.
Two clean, silent, collateral-destroying cases:

```
Thanks for the update on this.

To: recap, we need three approvals before Friday.
From: what I can tell, the budget already covers this.

We should have a decision by end of week either way.
```
→ `body_clean == "Thanks for the update on this."` — `quoted_signals=('header_block',)`,
`ambiguous_lines=0`. Both the recap sentences *and* the trailing paragraph are destroyed.

```
Thanks for the update on this.

Recap below.

Original Message

We agreed to renew at the same rate, and I still think that was the right call...

We should have a decision by end of week either way.
```
→ `body_clean == "Thanks for the update on this.\n\nRecap below."` —
`quoted_signals=('forward_separator',)`. A bare, dash-free "Original Message" used as a person's
own heading latches exactly like the client's own separator.

The other 20 of 27 sentences survive correctly, including calendar-masked first-person attacks in
Italian/Polish/Portuguese/Spanish-plural (locales the round-8 corpus doesn't cover) and vocabulary
collisions (`cc'd`, `subject to`, `reply-to`, `cheers`, `date night`) — the fix is not thin
everywhere, just at this one seam. **Filed R-ARCH-025, BLOCKER** (§4): this is the same defect
class as R-ARCH-022 — an ordinary two-line prose shape trips a latching structural signal with no
ambiguity flag — found by exactly the mechanism (a fresh corpus) this round's own work order
required.

## §4 — the false-negative re-measurement (Priority 4)

Independently reconstructed the 7×23 measurement from `CORPUS_WEEK`/`client_headers_for_weekday`
rather than trusting the shipped test (`/tmp/mailweave-review/latch/fn_check.py`). Confirmed
2026-08-24..30 is a real Monday–Sunday. 23 formats counted directly from the dict. **28/161 =
17.4%, exactly 4 formats, each surviving on all 7/7 days, zero weekday-dependence** — matches
HANDOFF exactly, and the "no address (21) / ordinal date (7)" split matches (3 formats × 7 +
1 format × 7 = 28).

## §5 — Part 4, the enumeration (Priority 5)

`uv run python -m tools.field_census` → **199**, matching the claim and the test-pinned
`AUDITED_FIELD_TOTAL`. `test_field_census.py`'s 6 tests pass, including the planted
unreadable-class probe (confirmed it actually raises `FieldCensusError` by reading the code, not
just trusting the green check).

Reintroduction: reverting the two new capabilities (constructor-parameter reading and the
raise-on-unrecognised-shape) together breaks 4, not 3 — but scoping the revert to exactly "a plain
class with its own `__init__` is silently skipped again" while leaving the raise live for classes
with no `__init__` at all (the planted probe's shape) reproduces **exactly 3**, matching the
claim. The 187-on-the-round-7-field-set claim is checked by the suite's own
`test_the_round_seven_reading_misses_exactly_the_hand_added_fields`, which recomputes the old
reading independently rather than calling the new `census()`; read it and it does what it claims.

## §6 — Findings

```
ID: R-ARCH-025 | Severity: BLOCKER | Rubric: WORK_ORDER Part 1 ("zero false positives on
sender-authored prose"); A5 | Location: content/quotes.py:743-793 (_header_block_start, _latch),
:461-471 (_SEPARATOR_LINE_RE)
Reproduction: §3 — /tmp/mailweave-review/latch/r_arch_round8_corpus.py, cases hb_recap_to_from
and fs_bare_original_message_heading, both positions
Expected: zero sender sentences removed (round 8's own gate, restated after R-ARCH-022)
Actual: 14/54 = 25.9% on a corpus of ordinary two-line prose and bare section headings; both
paragraphs before/after destroyed silently (ambiguous_lines=0), same shape as R-ARCH-022
Required fix: header_block's distinctness bar (≥2 fields) is necessary but not sufficient —
needs a check that the block's *values* look like real header content (a name, a date, a
subject), not merely that two lines start with different field-name-plus-colon prefixes; the
bare separator match needs the client's own dashes, not the bare phrase alone
```
```
ID: R-ARCH-026 | Severity: HIGH | Rubric: none — reported not gated per A5, but Priority 1 of
this round's own work order | Location: content/quotes.py:558-560 (LATCHING_SIGNALS), :905-943
(_segment)
Reproduction: §1 — /tmp/mailweave-review/latch/measure.py, 16/16 cases, 1251/1251 chars
Expected: the implementer's own framing — "a reviewer should attack this position first"
Actual: sender text written below any of the three latching signals is removed 100% of the
time in every shape tried (reply-below, signoff, interleaved); disclosed via
StripResult.latched/Reduction.detail, but body_clean itself does not contain it and no
production Gmail retrieval exists yet to exercise the unabridged path
Required fix: the implementer's own proposal — carry <blockquote> nesting out of
content/html_text.py as `>` markers so the bounded (non-latching) rule can apply instead of
the judgement-call latch; short of that, state the residual risk in the round's exit criteria
rather than letting it stand as unquantified
```

## Execution record

Commands: `uv sync`; `mailweave.__file__` check; `ruff check`/`format --check`; `mypy`; `pytest -m
"not network"` (823, twice); `python -m tools.guards`; `make check`. Files patched for
reintroductions, each run against the full suite and restored+diffed byte-identical before the
next: `content/quotes.py` (×4: header-block threshold, signature-delimiter prefix, loose
attribution at two different insertion points), `tools/field_census.py` (×2). Two standalone
scripts run from outside the tree against the installed package, never copied into `tests/`:
`r_arch_round8_corpus.py` (27 sentences) and `fn_check.py` (independent 7×23 false-negative
recomputation). `RELEASE_RUBRIC.md`/`FINDINGS_LEDGER.md`/`RUBRIC_TRANSITIONS.md` untouched.

## Per-criterion recommendations

| Criterion | Recommendation |
|---|---|
| A5 false-positive gate, as stated (3 named corpora, 2 positions) | **Met**, reproduced exactly: 0/200. |
| A5 false-positive gate, in substance (no sender text ever destroyed) | **Not met.** R-ARCH-025 destroys 25.9% of a fourth corpus via the same latching mechanism, undisclosed and untested by any of the three named corpora. |
| A5's latch (Priority 1) | Real, 100% destructive in every shape tried, and honestly disclosed — but disclosure is not a fix. HIGH rather than BLOCKER only because the round's own gate language scopes to the three named corpora and this is an out-of-scope position by that letter; the spirit is not met. |
| Layering fix (dependency removal, six-signal invariant) | **Confirmed genuinely closed.** No bypass; assertion is live; all three reintroduction counts reproduce exactly; round-7 BLOCKER sentence survives whole. |
| False-negative re-measurement | **Confirmed exactly**: 28/161 = 17.4%, uniform across all 7 weekdays, 4 formats, matches the declared two-shape residue. |
| Part 4 enumeration | **Confirmed exactly**: 199 on this tree, reintroduction counts match after correct scoping, planted-raise property verified by reading the code. |
| Overall Round 8 gate | **Does not close.** One new BLOCKER (R-ARCH-025) in the same defect class as round 7's, found in exactly the position the round's own process (a fresh corpus) exists to find it, plus one disclosed HIGH (R-ARCH-026) the implementer explicitly asked the next reviewer to attack and which does not survive the attack. Parts 2, 4, and the false-negative correction are all independently confirmed sound. |
