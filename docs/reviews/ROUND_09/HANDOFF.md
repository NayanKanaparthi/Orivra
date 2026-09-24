# ROUND 09 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_09/WORK_ORDER.md`, both parts.
Baseline in: `make check` green, 823 tests, 8 criteria PASS. Baseline out: `make check` green,
**1,168 tests**, 8 criteria PASS, no rubric row touched, no ledger row added.

Every number below was produced by running something. Where a claim could not be verified by
execution it says so.

> ### Correction, round 10 (R-ARCH-029) — "recoverable one class wider"
>
> **The recovery guarantee A7 rests on is containment, not "one widening always suffices".**
> The text is present in `body_clean.text` and `body_clean.view(list(SpanClass))` returns it
> exactly; *that* is what downgrades content loss from a blocker.
>
> Two claims in this document are one class wide, and both are true as written and as scoped:
> the seven **collateral neighbour** paragraphs, and `LATCH_CORPUS`'s 1,264 characters. What
> does not hold is the general reading — that a default-view miss is always one widening from
> being fixed. R-ARCH re-ran round 8's corpus against `ONE_WIDENING` and **all fourteen**
> misclassified entries still missed a fragment (eight wholly inside `quoted` spans; six split
> by a `forwarded` heading line). Reproduced in this tree at 14 of 14 and now measured in the
> suite by `test_one_class_wider_does_not_recover_the_misclassified_entries`.
>
> The three places below where the wording could be read generally are marked inline. Nothing
> in the round-9 measurements changes; only the framing does. — implementer, round 10

---

## Part 1 — amendment A7: the pipeline annotates, and does not delete

### What was built

| file | what it is |
|---|---|
| `server/src/mailweave/content/annotate.py` (new, 297 lines) | `SpanClass`, `AnnotatedSpan`, `AnnotatedBody`, `build_annotation`. **The containment gate lives in `AnnotatedBody.__post_init__`.** |
| `server/src/mailweave/content/quotes.py` (rewritten below its detectors) | `classify_lines` replaces `_segment`; `annotate_body` replaces `strip_quotes_and_signature`; `StripResult` is gone. Every regex, template and locale table is byte-identical to round 8. |
| `server/src/mailweave/content/pipeline.py` | `body_clean: AnnotatedBody`, new `default_view: str`; `normalise` moved *before* annotation; head truncation applies to the view. |
| `server/src/mailweave/errors.py` | `AnnotationContainmentError(ContentProcessingError)`. |
| `tests/test_a7_containment.py` (new, 301 tests) | the gate. |
| `tests/test_a7_default_view_quality.py` (new, 22 tests) | the reported numbers. |
| `tests/fixtures/reply_chains.py` | R-ARCH's fourth corpus and R-ARCH-026's latch corpus, both reconstructed and validated (below). |

`body_clean` is now the **whole body text with classified spans**. `ProcessedMessage.default_view`
is the string round 8 called `body_clean`; `body_tokens` counts it, so the disclosure budgets it
feeds are unchanged in meaning.

### How the containment gate is enforced

Three layers, in decreasing strength.

**1. The bad state is unrepresentable.** `AnnotatedBody.__post_init__` refuses any span set that
does not tile its text: contiguous from character 0, non-empty spans, ending at `len(text)`, and
`"".join(text[s.start:s.end] for s in spans) == text`. There is no constructor that skips it and
no `model_construct`-style bypass — it is a frozen dataclass whose `__post_init__` always runs. An
annotation that lost a character cannot be built, in the same way an `Envelope` that dropped a hit
cannot be built.

**2. The property is stated over generated input, not over a corpus.** This is the part that
matters, because rounds 5–8 each passed a corpus and were then defeated by one nobody had thought
of. `test_no_input_character_is_absent_from_the_annotated_output` runs 400 Hypothesis examples over
an alphabet containing the whole ASCII control range, the five non-`\n` Unicode line boundaries,
Latin-1 through U+2FFF and CJK. `test_the_gate_holds_over_generated_mail_shapes` runs another 400
over lists assembled from 30 real mail fragments — quote markers, three separator spellings, header
lines, four attribution formats, R-ARCH-025's two shapes, sign-offs — so the generator explores the
*structures* the classifier reacts to rather than only random noise. A third property asserts
`view(all classes) == text` for any input: the default view may be as small as it likes, the body
may not.

**3. The production path checks itself per message.** `process_message` asserts
`annotated.text is the text that entered the stage` and hands `reconcile` a declared removal of
**zero**, so a stage that started shrinking the body fails the pipeline instead of shipping a
shorter one.

**Verified live, not decorative.** Reintroducing deletion in `build_annotation` (drop the spans of
non-`original` lines — round 8's operation, one line):

```
1168 passed  ->  339 failed, 829 passed
```

both property tests, the pipeline stage test, the whole-pipeline test, and every corpus
restatement. `annotate.py` restored and diffed byte-identical afterwards.

`test_an_annotation_that_loses_a_character_cannot_be_constructed` additionally drives seven
distinct violations at the constructor — gap, short tiling, overlap, past-the-end, no spans for
non-empty text, empty span, span with no signal — and asserts each is refused with its own message.

### What the gate does **not** cover, stated rather than implied

The gate is over the **annotation stage**. The stages upstream of it still remove characters and
still declare each removal with a count: HTML→visible text, zero-width and bidi control stripping
(R-SEC-005), the charset ladder, NFKC, whitespace collapse. A7 replaced the operation that deleted
*sentences*; it does not make the charset ladder lossless, and claiming otherwise would be the
overclaim this round exists to stop.

The strongest whole-pipeline statement that is actually true is tested rather than asserted:
`test_the_whole_pipeline_keeps_every_visible_character` runs 200 Hypothesis examples of a
`text/plain` body over a visible, NFKC-stable alphabet (including accented Latin and CJK, so a
byte-indexing implementation fails it) and requires the non-whitespace character sequence of the
decoded body to equal that of `body_clean.text` exactly. It fails under the deletion
reintroduction above.

### The five classes, and why the latch is `uncertain`

| class | signals | in the default view |
|---|---|---|
| `original` | `no_structural_signal`, `attribution_shaped_unrecognised` | yes |
| `quoted` | `quote_marker`, `header_block`, `client_attribution` | no |
| `forwarded` | `forward_separator` | no |
| `signature` | `signature_delimiter`, `signature_sign_off` | no |
| `uncertain` | `forward_separator_unmarked_extent`, `header_block_unmarked_extent`, `client_attribution_unmarked_extent` | no |

`uncertain` is the region a client signal opened and **no client marked the end of**. Round 8
deleted exactly those characters and labelled them `quoted`; R-ARCH-026 then measured that they
contain the sender's own reply in 16 of 16 realistic cases. Calling them `quoted` and keeping them
would be asserting something measured to be wrong; `uncertain` is what the classifier actually
knows. Reverting the three to `SpanClass.QUOTED` fails 4 tests.

Amendment A5 survives A7 untouched and still governs what may leave the default view:
`classify_lines` raises if a non-`original` line carries a signal outside
`STRONG_STRUCTURAL_SIGNALS`. An attribution-*shaped* line matching no client format stays
`original` — A5 rules that shape alone may not cost a sender their words — and carries
`attribution_shaped_unrecognised`, which the pipeline still turns into a zero-sized `Reduction`
with a reason carrying no mail text.

### No tuning happened, and here is the check for it

`classify_lines` finds **exactly** the regions round 8's stripper deleted. Verified by running
round 8's `quotes.py` side by side with the new tree over 293 bodies — all four prose corpora in
both positions, the 26-case reply-chain corpus, and the 16-case latch corpus:

```
bodies compared: 293    default view differs on: 0
```

byte-identical in every case. So the default view reproduces round 8's `body_clean` and its token
economics, and the numbers below are directly comparable with round 8's destruction numbers rather
than measured against a moved goalpost.

### The reported numbers — default-view quality

Sender-authored prose across **four** corpora (three round-7/8 corpora plus R-ARCH's fourth), in
both positions, 254 entry/position pairs:

| corpus | entries | destroyed (round 8) | destroyed (A7) | absent from the default view (A7) |
|---|---|---|---|---|
| `implementer_round_7` | 36 | 0 | **0** | 0 |
| `r_arch_round_7` | 35 | 0 | **0** | 0 |
| `implementer_round_8` | 29 | 0 | **0** | 0 |
| `r_arch_round_8` (R-ARCH's fourth) | 27 | 7 per position | **0** | **7 per position** |
| **total, both positions** | **254** | **14 (5.5%)** | **0** | **14 (5.5%)** |

The two fourteens are the same fourteen cases. **R-ARCH-025 is not fixed and is not claimed to
be** — the two shapes it found (two consecutive prose lines opening with different header-field
names; a bare dash-free "Original Message" used as a person's own heading) still trip
`_header_block_runs` and `_SEPARATOR_LINE_RE`, and the default view is wrong on all seven entries.
What changed is that the sentences are in `body_clean`. On R-ARCH's own corpus alone the figure is
14 of 54 = **25.9%** — identical to round 8's destruction rate, because it is literally the same
misclassification with a different operation behind it.

**Collateral:** round 8 destroyed the unrelated paragraph *around* the sentence too. Seven such
neighbours are outside the default view; **all seven are `uncertain`, so widening the view by one
class returns every one.** *(Round-10 correction: true, and true only of these seven neighbours.
The fourteen misclassified entries themselves are **0 of 14** one class wider — R-ARCH-029.)*

**False negatives (client headers still shown), reported not gated:** **28 of 161 = 17.4%**, the
same four formats (`gmail_en_no_address`, `outlook_no_address`, `protonmail`, `thunderbird`), each
on all seven weekdays. Unchanged from round 8, as it should be — A7 changed no detection rule, and
a moved number here would have meant the classification *did* change.

### R-ARCH's fourth corpus: reconstructed, then validated before being trusted

The reviewer's file lived at `/tmp/mailweave-review/latch/r_arch_round8_corpus.py` and was never
committed, so `R_ARCH_ROUND_8_PROSE` is written from the published description in
`ROUND_08/R-ARCH.md` §3/§6 — 27 entries, the two named destructive shapes (two of them the
reviewer's verbatim reproductions), the calendar-masked first-person attacks in it/pl/pt/es-plural,
and the five vocabulary collisions it lists. **Run against round 8's stripper it destroys 14 of 54
= 25.9% through exactly 7 entries in both positions**, matching R-ARCH's published figure and its
"the other 20 of 27 survive correctly". It is not character-identical to R-ARCH's file and does not
claim to be; what it reproduces is the measurement.

### R-ARCH-026: did the latch dissolve? Verified, and the answer is *half*

`LATCH_CORPUS` reconstructs the sixteen cases: all three latching signals in reply-below,
sign-off, interleaved and postscript positions, plus four combined shapes. Against round 8's
stripper it destroys **1,264 of 1,264** tagged sender characters — 100%, at R-ARCH's scale
(they measured 1,251/1,251 with their own sentences).

| | round 8 | A7 |
|---|---|---|
| tagged sender characters **destroyed** | 1,264 / 1,264 | **0 / 1,264** |
| present in `body_clean.text` | 0 | **1,264 / 1,264** |
| shown in the default view | 0 | 0 / 1,264 |
| shown one class wider (`original + uncertain`) — **this corpus only** | not possible | **1,264 / 1,264** |
| returned by `view(list(SpanClass))` — the actual guarantee | not possible | **1,264 / 1,264** |

**The latch dissolves as a destruction mechanism and does not dissolve as a default-view
problem.** The extent is still judged, on the same three signals, in the same place — the
classifier got no better at guessing where an unmarked quoted block ends. What changed is that
being wrong now costs a **view** rather than the sentence — the characters are present, and a
view over every span class returns them. *(Round-10 correction: the 1,264/1,264 one class wider
is a property of this corpus, where every tagged character sits strictly inside an unmarked
extent by construction. It does not generalise to default-view misses — R-ARCH-029.)* All sixteen cases report `latched is True`, every span covering
a tagged fragment is `SpanClass.UNCERTAIN`, and the signal names which latch opened it. This is
stated as a live measurement in `test_the_latch_still_gets_the_default_view_wrong_and_that_is_the_honest_number`
rather than as a paragraph, and it is the number the next reviewer should attack.

---

## Part 2 — A6's retention holes

### R-SEC-029 — every Unicode line boundary

`_sealed_scalar` now refuses any value where `value.splitlines() != [value]`. Comparing against
the list, not its length, also catches a *trailing* break (`"one\n".splitlines()` is `["one"]`,
length 1). The definition is the runtime's, not a transcribed set, which is the point: the next
boundary character Unicode defines is covered without anyone remembering to add it.

`test_the_line_check_is_the_runtimes_definition_and_not_a_transcribed_list` walks all 12,288 code
points from U+0000 to U+2FFF and asserts the predicate agrees with `str.splitlines()` on every one.

**Reintroducing `"\n" in value or "\r" in value`: 7 failed** (one per boundary code point, the
range property, and the id-bound test which uses a U+2028 probe).

### R-SEC-030 — `history_id` and `internal_date` validated to their real formats

New `_sealed_numeric_id`: the `_sealed_scalar` floor, then `^[0-9]{1,20}$`. **ASCII** digits
deliberately — `"١٣".isdigit()` and `"²".isdigit()` are both `True` and neither is anything Gmail
emits, so writing the check as "digits" would have committed this project's own defect inside the
fix for it. Both are probed by name. 20 is the width of a uint64 in decimal, which is what a
`historyId` is; an `internalDate` is milliseconds since the epoch, rendered the same way.

The reviewer's 49-character sentence is refused under both field names, and the parametrised probe
covers eleven near-miss shapes (digits with a tail, a sign, scientific notation, leading and
trailing space, hex, Arabic-Indic digits, a superscript, 21 digits).

**On the STUB row** — the review's "fix or document" alternative, answered on the record in
`_sealed_numeric_id`'s docstring and executed in
`test_a_stub_rows_internal_date_can_only_be_a_timestamp`. The field stays on stub rows, and that is
a decision rather than an oversight: with the shape check it can only be a decimal millisecond
count, which is the same class of bookkeeping scalar as the `position` a stub already carries.
Contract R-04's stub tier withholds *content*, and a timestamp is not content. What made the
finding real was that the field was unchecked, not that stubs carry a date — so the check is the
fix and the reasoning is written down rather than left to be rediscovered.

**Reintroducing the missing shape check: 13 failed.**

### R-SEC-031 — the seal's id fields, bounded, and the test's claim made true

`_ids`, `_thread_id` and `_thread_ids` now go through `_sealed_id`: non-empty, ≤ 64 characters,
single line by the same `splitlines()` definition. Deliberately **no** character-class check —
this repository's fixtures and every reviewer probe use ids like `"m1"` and `"ghost-1"`, and a hex
check here would refuse the tests that attack the ledger rather than any attack. What R-SEC-031
found was the *absence of a bound*, and a bound is what it gets: five lines of mail text no longer
fit, which was the reproduction.

The round-8 reflection test is replaced rather than patched, because its problem was the shape of
its claim. It walked one well-formed observation and asserted the values it found were bounded —
which is true of any well-formed fixture and proves nothing about the constructor. The new pair:

- `test_no_string_bearing_slot_of_the_seal_accepts_mail_text` drives **three probes at each
  string-bearing slot by name** (a five-line body, a 4,096-character single line, and a value whose
  only defect is a U+2028), through the constructor keyword that writes that slot;
- `test_every_slot_of_the_seal_is_either_probed_or_cannot_hold_a_string` asserts every remaining
  slot holds something that is not a string, with `ObservedEndpoint` exempted **by name** as a
  closed vocabulary rather than skipped silently.

Together they say "every string this object can retain is bounded", which is what round 8's
docstring claimed and its exemption list contradicted.

**Reintroducing all four unbounded fields: 5 failed**, named per slot.

### One thing fixed beyond the three findings, and why

`FetchedIds.next_page_token` was the **fourth** unbounded string in the same object, and round 8's
reflection test skipped it silently because its fixture is a `threads.get`, which has no page
token. It is bounded now (`_sealed_page_token`: non-empty, single line, ≤ 256 characters). This is
inside the object R-SEC-031 names and the reflection test cannot make an honest coverage claim
without it, which is why it was fixed rather than only reported.

**Stated honestly:** a Gmail continuation token has no documented shape, so unlike every other
sealed string it gets only the floor. 256 single-line characters is a place a sentence fits. This
field is *narrowed*, not closed, and it is the weakest string bound in the seal.

---

## The "one shape validated, its peers trusted" sweep

Swept: every literal `\n`/`\r` check, every `isdigit`/`isascii`/`isalpha`/`isspace` call, every
`Field(min_length=...)` without an upper bound, every timestamp-shaped field against
`parse_instant`'s coverage, the fence, and the invisible-character sets. Four instances found
beyond the three fixed. **All four are reproduced by execution; three are recorded and left**, per
the work order's scope discipline.

### S-1 — `next_page_token` (FIXED, above)

### S-2 — `strip_invisible_characters` covers 16 hand-listed code points; Unicode has 170 (LEFT)

`content/html_text.py` lists five zero-width characters and eleven bidi controls. **154 Unicode
`Cf` format characters are not stripped**, and the misses include the closest possible peers:

- **U+061C ARABIC LETTER MARK** — a bidi control, the direct sibling of the eleven that *are*
  listed, absent;
- **U+00AD SOFT HYPHEN** — invisible in every renderer;
- the whole **U+E0000–U+E007F tag block**, which encodes an invisible ASCII payload.

Reproduced: `strip_invisible_characters("Pay ­now" + <"HIDDEN" as tag characters>)` returns
`removed_chars=0` and the tag characters survive into `body_clean`. This is R-SEC-029's exact shape
one module over — a set somebody typed out, with the next character silently absent — and it bears
on INJ-04/R-SEC-005 rather than on A6. **Left**: it is not in either part of this work order, and
the right fix (strip by `unicodedata.category(c) == "Cf"` minus a deliberate keep-list, with its
own reduction accounting and its own false-positive measurement) is a change with a measurement
attached, not a one-liner to ride along in a structural refactor.

### S-3 — `HistoryAddition.history_id` is the same field name, unvalidated, and reaches the wire (LEFT)

`envelope/reasons.py:106` declares `history_id: str = Field(min_length=1)`. Reproduced:

```python
HistoryAddition(history_id="Please review the attached NDA before end of day.").render()
# 'history.list messagesAdded since historyId Please review the attached NDA before end of day.'
```

A U+2028-separated two-sentence value is accepted too. This is R-SEC-030 exactly, one layer up: the
seal's `history_id` is now digit-checked and the *reason*'s peer of the same name is not, and the
reason renders onto the wire. **Left** per scope discipline — it is not one of the three named
findings — but it is the sweep's most directly actionable result and a reviewer should expect to
find it. The fix is one field validator using the same `^[0-9]{1,20}$`.

### S-4 — `StoredCredentials.obtained_at` is an unvalidated timestamp beside two validated ones (LEFT)

`Source.fetched_at` and `Source.verified_at` are `parse_instant`-checked, and the seal's
`fetched_at` is too. `auth/tokenstore.py:55`'s `obtained_at` is `str = Field(min_length=1)` and is
never parsed. Same class, lower stakes (it is local credential bookkeeping, not disclosed output).

### S-5 — `isdigit()` accepts a representation `int()` rejects (LEFT)

`auth/tokenstore.py:131`: `if len(fields) != 2 or not fields[0].isdigit(): continue`, then
`int(fields[0])`. `"²".isdigit()` is `True` and `int("²")` raises `ValueError` — so a file named
`.mailweave-tokens.².tmp` in the credential directory raises an uncaught `ValueError` out of
`sweep_orphaned_temporaries`, whose own docstring says "every error is swallowed", and which is
called from `save()`. Reproduced at the interpreter, not in the store. Low severity, in the
credential path, and it is the same "one representation checked" habit — which is the point of
recording it.

### Also swept, nothing found

`fence.py`'s nonce containment is a substring check against the exact nonce, which is
representation-complete. One adjacent observation without a reproduction: `Envelope.fence_nonce` is
`Field(min_length=8)` while `mint_nonce()` produces `mw-` plus 16 hex characters, so the minter has
a shape the field does not require. No exploit was constructed and it is recorded as an
observation, not a finding.

---

## Defects found and deliberately left

Beyond S-2..S-5:

1. **R-ARCH-025 is open.** Under A7 it costs a wrong default view rather than the sentence, so it
   is reported at 14/254 rather than gated. The fix R-ARCH proposed — check that a header block's
   *values* look like header content, and require the client's own dashes on a separator — was not
   attempted this round, because tuning the rule is exactly what rounds 5–8 did.
2. **Documentation drift about the stripper.** `README.md` WS-07 and `ARCHITECTURE_DECISION.md`
   D.4a step 6 both describe quote *stripping*; `IMPLEMENTATION_PLAN.md` WS-07 still names
   `email_reply_parser`, which R-ARCH flagged in round 8 as the orchestrator's item and which is
   still unfixed. A7 is recorded in `ARCHITECTURE_AMENDMENTS.md`, which is where amendments live,
   and no doc was edited this round.
3. **`ReductionKind` was not extended.** A7's classification records ride on the existing `QUOTED`
   and `SIGNATURE` kinds with `removed_chars=0` and `count` = characters classified, and the detail
   names the span class and says the text is present in `body_clean`. Adding a `SPANS_CLASSIFIED`
   kind would be a schema change in a structural refactor; it is the right change and it is not
   this round's.

---

## Where this work is weakest

**First, and worth attacking first: `uncertain` is invisible by default, and that is a choice A7's
text underdetermines.** A7 says the default view is `original` spans. The classifier puts the
*entire* unmarked extent of a forward or an Outlook header block into `uncertain`, which means a
real forwarded thread's whole body is hidden by default — correct — and the sender's own reply
below it is hidden too — wrong, in 16 of 16 measured cases. I chose the class boundary so that the
default view reproduces round 8's `body_clean` byte for byte, on the reasoning that "reproduces
today's token economics" is A7's own stated requirement and it makes every number comparable. A
reviewer could reasonably argue the default view should be `original + uncertain`, which would show
100% of R-ARCH-026's tagged characters at the cost of showing every unmarked quoted body. Both
positions are defensible; only one is implemented, and the measurement for the other is in the
suite (`ONE_WIDENING`). *(Round-10 correction: `ONE_WIDENING` measures that alternative for the
latch shape, not the recoverability of default-view misses generally — R-ARCH-029.)*

**Second: the two reconstructed corpora are reconstructions.** R-ARCH's fourth corpus and the
latch corpus were never committed to this tree. Both reproduce the reviewer's published figures
exactly against round 8's code — 14/54 = 25.9%, and 1,264/1,264 = 100% — which is strong evidence
they are faithful *as measurements*. They are not the reviewer's sentences. If R-ARCH's real corpus
contains a shape mine does not, this round's 5.5% is optimistic by that shape.

**Third: the whole-pipeline containment property is alphabet-restricted.** The stage-level gate
takes arbitrary input. The whole-pipeline one restricts to visible, NFKC-stable characters, because
NFKC folding and invisible-character stripping are real transformations and asserting past them
would be false. That restriction is honest but it is a restriction, and S-2 above shows the
invisible-character stage has its own hole that the restricted alphabet cannot see.

**Fourth: `default_view` is rendered by re-running `normalise` over the joined spans.** Dropping
spans leaves the blank lines that flanked them, and the pipeline folds them with the same
normaliser that produced the body's whitespace. It is correct on all 293 bodies measured and it is
a second place whitespace policy is applied. A future view with different classes gets the same
treatment, which may not be what a caller wants from a `body_full` view.

**Fifth: A7's disclosure-layer half is a seam, not an integration.** `body_clean` has no consumer
outside `content/` and the tests — the envelope layer takes `Content.text` from a caller, and no
Gmail retrieval exists. So "the disclosure layer chooses which spans to show, via its existing
budgets and depth vocabulary" is implemented as `AnnotatedBody.view(classes)` plus a `default_view`
the pipeline renders, and **nothing in `envelope/` calls it yet**. The `Depth` vocabulary is not
wired to `SpanClass`. That mapping is the obvious next piece of work and R-DISC should read this
paragraph before assessing whether A7 composes with the depth vocabulary: what exists is the shape
it will compose through, not the composition.

---

## Execution record

`make check` green at every checkpoint and at the end: `ruff check`, `ruff format --check` (95
files), `mypy --strict` (69 source files), `pytest -m "not network"` **1,168 passed**,
`python -m tools.guards` (7 guards clean), `tools/rubric_status.py --check` (8 PASS / 105 NOT
TESTED / 10 transitions — unchanged).

Reintroduction counts, each produced by editing the file, running the full suite, restoring, and
diffing byte-identical:

| defect reintroduced | failures |
|---|---|
| deletion in `build_annotation` (A7's gate) | **339** |
| unmarked extents classified `quoted` rather than `uncertain` | 4 |
| newline check back to `"\n" in value or "\r" in value` (R-SEC-029) | 7 |
| numeric shape check removed from `history_id` / `internal_date` (R-SEC-030) | 13 |
| the four seal strings unbounded again (R-SEC-031 + S-1) | 5 |

New test files: `test_a7_containment.py` (301), `test_a7_default_view_quality.py` (22),
`test_seal_retention_round9.py` (21). Rewritten: `test_quote_corpus.py` (162),
`test_sealed_scalars_a6.py` (25).

`RELEASE_RUBRIC.md`, `FINDINGS_LEDGER.md` and `RUBRIC_TRANSITIONS.md` were not written to. No
network in any test. No personal mail content anywhere: every corpus line is invented for this
repository.
