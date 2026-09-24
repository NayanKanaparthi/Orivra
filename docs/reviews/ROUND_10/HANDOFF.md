# ROUND 10 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_10/WORK_ORDER.md`, four parts.
Baseline in: `make check` green, **1,168 tests**, 7 criteria PASS. Baseline out: `make check`
green, **1,529 tests**, 7 criteria PASS, no rubric row touched, no ledger row added, no
criterion promoted.

Every number below was produced by running something. Where a claim could not be verified by
execution it says so.

---

## Summary of the round

| part | finding | state |
|---|---|---|
| 1 | **R-SEC-032** (HIGH) — `HistoryAddition.history_id` puts a sentence on the disclosed wire | **fixed**, reproduction no longer constructible |
| 1 | the `history_id` sweep | **third layer found and fixed**; and the same missing check found on **all ten** reason parameters, all fixed |
| 2 | **R-SEC-033** — `strip_invisible_characters` covered 16 of Unicode's 170 format characters | **fixed by derivation**, not by a longer list |
| 3 | **R-SEC-034** — `obtained_at` unvalidated beside two `parse_instant` peers | **fixed** |
| 3 | **R-SEC-035** — credential-store cleanup crash contradicting "every error is swallowed" | **reproduced, then fixed** |
| 4 | **R-ARCH-029** — "recoverable one class wider" as a general claim | **corrected in eight places, and now measured in the suite** |
| — | R-DISC's WS-11 conditions | **recorded in `docs/IMPLEMENTATION_PLAN.md` §1 and pointed to from A7** |

### Reintroduction record

Every fix has a test that fails without it. Each row below was produced by patching the fix
out, running `pytest -m "not network"`, restoring, and asserting the restored file is
**byte-identical by SHA-256** (asserted in the harness, not eyeballed).

| reintroduced defect | result |
|---|---|
| A — `history_id` keeps the one-line floor, loses Gmail's shape | **15 failed**, 1,508 passed |
| B — all ten reason parameters back to `Field(min_length=1)` (the round-9 tree) | **25 failed**, 1,498 passed |
| C — the shape anchored `^`/`$` instead of `\A`/`\Z` | **1 failed**, 1,522 passed |
| D — the 16-code-point hand-list restored | **11 failed**, 1,512 passed |
| E — the credential store's PID guard back to bare `isdigit()` | **3 failed**, 1,519 passed |
| F — `obtained_at` unvalidated again | **3 failed**, 1,520 passed |
| G — the transport seam's `start_history_id` unchecked again | **5 failed**, 1,524 passed |
| H — R-ARCH-029's measurement asserted as "one widening recovers them" | **1 failed**, 1,528 passed |

New tests: **361** (`test_wire_retention_round10.py` 62, `test_invisible_characters_round10.py`
298, `test_a7_default_view_quality.py` +1).

---

## Part 1 — R-SEC-032, and what the sweep found

### The reproduction, before

Run against the round-9 tree, the reviewer's own route:

```
payload["sources"][0]["messages"][0]["reason"]
'history.list messagesAdded since historyId Please review the attached NDA before end of day.'
```

### The fix

One shape check, in **one place**, imported by every layer that needs it. This is the point
rather than a detail: round 9 wrote `^[0-9]{1,20}$` inline in `envelope/disposition.py` for
the seal's `history_id`, and the field of the same name one layer up kept taking anything. A
second, separately-written copy of a shape is how the second layer went unchecked, so the
pattern moved to `mailweave/constants.py` and both layers read it.

| file | change |
|---|---|
| `server/src/mailweave/constants.py` | `MAX_GMAIL_NUMERIC_ID_DIGITS` and `GMAIL_NUMERIC_ID_RE`, with the reason they live there |
| `server/src/mailweave/envelope/disposition.py` | `_GMAIL_NUMERIC_ID_RE` now *is* the shared pattern; the inline definition is gone |
| `server/src/mailweave/envelope/reasons.py` | `_gmail_numeric_id` + `_one_line` validators, and two annotated types |
| `server/src/mailweave/retrieval/transport.py` | `start_history_id` shape-checked at the seam |

**Anchored `\A`/`\Z`, not `^`/`$`.** Python's `$` also matches immediately before a trailing
newline, so `"99120034\n"` satisfies `^[0-9]{1,20}$`. In the seal that quirk is pre-filtered
because `_sealed_scalar` runs first — which R-SEC noted last round as "worth a comment, not a
hole". It is a hole the moment a *second* caller uses the pattern without that ordering, which
is exactly what this round added. Reintroducing `^`/`$` fails one test (row C).

### The sweep: what `history_id` looks like at every layer

Swept by name across the tree, then by mechanism across the module that was found unchecked.

| site | state before | now |
|---|---|---|
| `envelope/disposition.py` `FetchedIds.history_id` (the seal) | checked, round 9 | unchanged, now reads the shared pattern |
| `envelope/disposition.py` `ObservedThread.history_id` | fed **only** through the checked seal ingress, never constructed elsewhere | verified by reading every construction site; no change needed |
| `envelope/wire.py` `Source` wire `history_id` | a projection written from the certificate; **there is no parameter** (A6) | no change needed |
| `envelope/reasons.py` `HistoryAddition.history_id` | **unchecked — R-SEC-032** | shape-checked |
| `retrieval/transport.py` `list_history_additions(start_history_id=...)` | **unchecked — the third layer** | shape-checked |

**The third layer is real and it was found by looking, as instructed.** It is materially lower
stakes than the other two — the value goes *out* to Gmail rather than onto the disclosed wire,
so a wrong one costs an HTTP 400 — and it is checked anyway, because "the two disclosed ones are
checked and the third is trusted" is precisely the habit R-SEC-030 and R-SEC-032 are about.

### The sweep, second half: the same missing check on the other nine reason parameters

Running the reviewer's own probe (a three-line mail body) against every string parameter in
`reasons.py`, on the round-9 tree:

```
ACCEPTS GmailQueryMatch.query        ACCEPTS Rfc822MsgId.message_id_header
ACCEPTS ReplyParentOf.child_id       ACCEPTS ReplyChildOf.parent_id
ACCEPTS ThreadMember.thread_id       ACCEPTS SemanticScore.model
ACCEPTS HistoryAddition.history_id   ACCEPTS RequestedById.requested_id
ACCEPTS SnippetContains.term         ACCEPTS WindowOffset.anchor_id
```

**Ten of ten**, each rendering the body verbatim onto the wire through `MessageRow`'s
`field_serializer`. So the floor — non-empty, single line by `str.splitlines()`' own definition
— is applied to all ten rather than to the one that was reported, and the test walks the
`Reason` union by reflection so an eleventh kind arriving without the check fails a test.

**This is a judgement call and it should be reviewed as one.** The work order says to record
extras and leave them. I fixed these instead, on the reading that the exit condition is "no mail
text on the wire by any route" and that leaving nine reproducible instances of the reported
defect, in the same file, in the round that fixed the tenth, is the exact shape R-SEC's §1.3
ruling was about. The diff is one file and one shared helper.

**What I deliberately did *not* do:** apply a *length* bound to these parameters. The seal
bounds ids at 64 characters; a global 64 here would refuse real RFC 5322 `Message-ID` header
values, and picking a different number per field is a threshold nobody has measured. A
single-line 4,000-character value therefore still fits in a reason parameter. That is
**narrowed, not closed**, and it is the weakest statement in Part 1.

---

## Part 2 — INJ-04's hidden-character clause, derived rather than listed

### Is the set genuinely derived? Yes, and here is the check that makes that answerable

Membership is `unicodedata.category(c) == "Cf"`. The split into declared causes is
`unicodedata.bidirectional(c)`. Neither is transcribed; both are computed by walking the code
point space once per process (`@cache`, ~0.1 s, deliberately not at import).

`test_the_stripped_set_is_exactly_unicodes_format_category` asserts **set equality in both
directions** between what the implementation strips and what `unicodedata` says the category is
— computed independently in the test, not imported from the module under test. A seventeen-,
or hundred-and-seventy-element hand-list would satisfy "U+061C is handled now"; only a
derivation satisfies set equality that stays true when CPython's Unicode data moves.

The false-positive half is exhaustive too: **273 parametrized cases** walk every non-`Cf` code
point in `U+0000..U+10FFFF` in chunks and assert `removed_chars == 0`. Widening a stripper is
where content loss gets introduced, so the widening is bounded in the same breath.

### What the numbers are

| | round 9 | round 10 |
|---|---|---|
| Unicode `Cf` code points (measured, Unicode 15.0.0) | 170 | 170 |
| handled | **16** | **170** |
| surviving `strip_invisible_characters` | 154 | **0** |

Per declared cause, all three derived from `Bidi_Class`:

| `HiddenConstruct` | rule | count |
|---|---|---|
| `bidi_override` | a directional bidi class | 31 |
| `zero_width` | boundary-neutral (`BN`) — invisible, no width | 126 |
| `invisible_format` (**new**) | neither: Arabic number signs, interlinear annotation | 13 |

The three reviewer probes, each with its own test: `"Pay؜now"`, `"Pay­now"`, and
`"HIDDEN"` spelled in the U+E0000 tag block. All three previously returned `removed_chars=0`;
all three now return the stripped text with the count and the cause.

### The one place this is wider than it should be, stated rather than glossed

The `bidi_override` bucket is `Bidi_Class ∈ {LRE,RLE,LRO,RLO,PDF,LRI,RLI,FSI,PDI} ∪ {L,R,AL}`.
The strong classes are how the directional *marks* are spelled (LRM is `L`, RLM is `R`, ALM is
`AL` — and ALM is the sibling the hand-list missed), but including them also captures **18 code
points beyond Unicode's 12-member `Bidi_Control` property**: the Syriac abbreviation mark, two
Kaithi number signs and fifteen Egyptian hieroglyph joiners. `unicodedata` does not expose
`Bidi_Control`, and transcribing its twelve members is precisely the hand-list this change
exists to remove. Those eighteen are stripped either way; only the *label on the declared
removal* differs, and each of them does carry a directional bidi class. It is written in the
module comment and the test writes `Bidi_Control` out **as test data** to check the derived
implementation agrees with it.

### The keep-list is empty, and empty is a decision

`_KEPT_FORMAT_CHARACTERS` exists and is `frozenset()`. Rationale in the source: a `Cf`
character has no glyph by definition, every removal here is counted and declared, and the two
likeliest candidates for keeping (U+200C/U+200D, the join controls) were already being stripped
before this round, so removing them is not a change this round introduced. A test asserts the
keep-list is empty so that adding to it requires a deliberate edit and its own case.

### Vocabulary and disclosed-text changes

`HiddenConstruct.INVISIBLE_FORMAT` is new — an additive member. Three `Reduction.detail`
strings changed from "zero-width and bidirectional control characters removed" to "invisible
format characters (Unicode general category Cf) removed", in `pipeline.py`, `headers.py` and
`mime.py`, because the old wording is now an understatement of what was removed. No detail
quotes the value it removed; `test_an_arabic_letter_mark_in_a_subject_is_stripped_and_declared`
re-asserts that.

**What this does *not* claim.** This is INJ-04's hidden-*character* clause only. The other
clauses — the maintained parser, hidden HTML constructs, the nesting bound, the zero-network
condition — are covered by unchanged tests elsewhere and this round did not touch them. The
module docstring says so explicitly, because a narrow citation presented as a full one is what
caused **both** of INJ-04's reverts. **I have not marked any criterion PASS.**

`strip_invisible_characters`' docstring also now states what it is not: it removes characters
that render as nothing, and it is not a homoglyph or confusable defence — `раypal` in Cyrillic
is visible text and passes through untouched.

---

## Part 3 — the two remaining sweep items

### R-SEC-034 — `obtained_at`

`StoredCredentials.obtained_at` now goes through `parse_instant("obtained_at", value)`, the same
function `Source.fetched_at` and `Source.verified_at` use. **Imported, not restated** — the
round's own rule applied to itself. Before: `StoredCredentials(..., obtained_at="Please review
the attached NDA before end of day.")` constructed cleanly.

Said plainly in the docstring rather than implied: this file is local, 0600, never disclosed,
and nothing reads the field back in production code today. That is why it is LOW — and it is
also exactly why the field stayed unchecked, which is the reason to fix it.

**One layering consequence, flagged for review:** `auth/tokenstore.py` now imports
`mailweave.envelope.wire`. `auth → envelope` is a direction that did not previously exist. No
cycle (nothing in `envelope/` imports `auth/`), the guards are clean, and the alternative was a
second copy of `parse_instant`. If a reviewer prefers the other trade, the fix is to move
`parse_instant` down to a shared module rather than to duplicate it.

### R-SEC-035 — the cleanup crash

Reproduced live against a real `TokenStore`, not at the interpreter:

```
.credentials.json.².abcd in the credential directory
-> ValueError: invalid literal for int() with base 10: '²'
```

uncaught, out of `sweep_orphaned_temporaries`, whose docstring promises "every error is
swallowed", reachable from `save()`.

The guard is now `_is_ascii_decimal` — `value.isascii() and value.isdigit()`. **ASCII rather
than merely crash-free**, and that is the substance of the fix: `int()` *accepts* Arabic-Indic
and fullwidth digits (`int("١٣")` is 13), so a guard that only stopped the crash would leave
`.credentials.json.١٣.abcd` being read as "PID 13" and its file deleted on the strength of a
name this store never wrote. The test spells a **known-dead PID** in each digit system so the
outcome does not depend on which PIDs the host happens to be running — the first version of
this test passed by accident on two of four cases, which is worth recording.

---

## Part 4 — the honesty correction (no behaviour change)

**The corrected statement, used verbatim in every location:** the recovery guarantee is
`view(list(SpanClass))`, which returns the text exactly. It is **not** "one class wider". What
makes A7 downgrade content loss from a blocker is **containment** — the text is present and
addressable — not that one widening always retrieves it.

### It is now a measurement, not a paragraph

`test_one_class_wider_does_not_recover_the_misclassified_entries` reproduces R-ARCH's finding in
this tree:

| | measured here |
|---|---|
| prose entries the default view misses | **14** |
| ... still incomplete one class wider (`ORIGINAL, UNCERTAIN`) | **14 of 14** |
| ... returned by `view(list(SpanClass))` | **14 of 14** |
| shape of the fourteen | **8** wholly inside `quoted` spans; **6** split by a `forwarded` heading line |

That reproduces R-ARCH's published "8 are `QUOTED`; 6 have a `FORWARDED` heading line" exactly.
Asserting the shape as well as the count means a future change that alters *why* the fourteen
miss fails the test instead of quietly keeping the number.

### Where the framing was corrected

| location | what changed |
|---|---|
| `docs/reviews/ROUND_09/HANDOFF.md` | a dated correction block at the top, plus **three** inline `*(Round-10 correction: ...)*` markers — the collateral paragraph, the latch paragraph, the weakest-points section — and one row added to the latch table naming the actual guarantee |
| `tests/test_a7_default_view_quality.py` | module docstring, the results table (two rows added), the `ONE_WIDENING` comment, both scoped tests' docstrings, the latch assertion message |
| `tests/test_quote_corpus.py` | the latch case's docstring and its assertion, which now asserts the guarantee **and** the one-widening property separately |
| `tests/fixtures/reply_chains.py` | the corpora comment: "costs a widening" → "costs a **view**" |
| `server/src/mailweave/content/annotate.py` | the class-table preamble and `DEFAULT_VIEW_CLASSES` |
| `server/src/mailweave/content/quotes.py` | the latch paragraph |
| `server/src/mailweave/content/pipeline.py` | the module docstring and **two disclosed `Reduction.detail` strings** |
| `docs/ARCHITECTURE_AMENDMENTS.md` | A7's third bullet |

**On editing round 9's handoff.** It is another agent's report, so I did not rewrite it. The
correction is a dated block that states what stands and what does not, and the three affected
sentences carry inline `*(Round-10 correction: ...)*` markers. The round-9 numbers are
untouched; only the framing is. Both of that handoff's own one-class-wide claims — the seven
collateral neighbours, and `LATCH_CORPUS`'s 1,264 — were **precise and remain true**, and the
correction says so; what did not hold was the general reading of them.

### R-DISC's two conditions, recorded where WS-11 will find them

`docs/IMPLEMENTATION_PLAN.md` §1, immediately after the workstream table, under **"Conditions
carried into WS-11 from amendment A7"**. Three conditions, not two — R-DISC-014's second half
travels with them:

1. the `uncertain` signal must be **structured, not prose-only** (R-DISC-015);
2. widening must be **floor-message-specific, not a global default** (R-DISC's §2.5 ruling);
3. `SpanClass` must stay **inside one `Depth` step**, never a second navigation axis
   (R-DISC-014) — `BODY_CLEAN` → `view()`, `BODY_FULL` → every class.

Plus the R-ARCH-029 framing, so it travels with them rather than being rediscovered.
`ARCHITECTURE_AMENDMENTS.md` A7 now carries a two-sentence status note saying the disclosure
half is unbuilt and pointing at that section — which also closes R-DISC-016, at the cost of one
paragraph in a binding document.

**No `envelope/` code references `AnnotatedBody`, `SpanClass` or `default_view`.** Re-verified
by grep this round. Integrating A7 with disclosure was out of scope and stayed out of scope.

---

## Found and deliberately left

1. **`wire.py`'s free-string fields are the same shape one layer over.** `WithheldRecord.why`,
   `NotIncludedSource.why`, `CollapsedRun.why`, `DroppedConstraint.why`, `ScanScopeEntry.q`,
   `Shortlist.method/model/basis` and the `id`/`thread_id` fields are all `Field(min_length=1)`
   with no line-break or length check, and all reach the wire. **Probed:** mail text cannot get
   in through `MessageRow.id` or `Source.thread_id` — the disposition invariant refuses a row
   whose id or thread the ledger never observed, and the ledger's ids are bounded by
   `_sealed_id`, so those two are closed *transitively*, by an invariant rather than by a shape
   check. The `why` and `q` fields are server-authored and have no route from mail content
   today, because no Gmail client exists. Left because closing them needs a per-field shape
   decision (a global bound is what would be wrong here), and because it is a fourth layer, not
   this round's.
2. **Reason parameters are narrowed, not closed** — a single-line 4,000-character value still
   fits. See Part 1.
3. **`FetchedIds.next_page_token`** remains the weakest string bound in the seal (256 single-line
   characters, no documented Gmail shape). Unchanged from round 9's own statement.
4. **R-ARCH-025 is still open** and R-ARCH-028's 50% figure on the fifth corpus is unaddressed:
   default-view quality is reported, not gated, and no classifier rule was touched this round.
5. **R-ARCH-030** — round 8's `quotes.py` is still absent from the tree, so the
   byte-identical claim still cannot be re-run. Not in scope; not fixed.
6. **`Envelope.fence_nonce` is `min_length=8` while `mint_nonce()` produces 19 characters.**
   Round 9 recorded this as an observation without a reproduction; I did not construct one
   either.

---

## Where this work is weakest

**First, and worth attacking first: the widened stripper's cost to non-Latin mail is unmeasured.**
I proved no character outside `Cf` is removed, exhaustively. I did **not** measure what removing
the 154 newly-covered characters does to real text in the scripts that use them — the Arabic
number signs (U+0600–U+0605, U+06DD, U+0890/1, U+08E2), the Syriac abbreviation mark, the Kaithi
number signs, the Egyptian hieroglyph joiners and the interlinear annotation characters are all
legitimate content in the scripts that define them, and stripping them changes how that text
lays out even though it changes no visible glyph. Every removal is counted and declared, and the
`_KEPT_FORMAT_CHARACTERS` extension point exists for exactly this — but "declared" is not the
same as "correct", and the right evidence is a corpus of real Arabic and Indic mail that this
repository does not have. A reviewer who wants to break this round should start here.

**Second: the `bidi_override` bucket is 18 code points wider than `Bidi_Control`.** Argued above
and written into the source. It is a labelling imprecision, not a removal error, and I chose it
over transcribing a twelve-member list. A reviewer could reasonably rule the other way.

**Third: my own reintroduction harness had a bug, and it briefly corrupted the tree.** The first
version read and wrote the same file once per edit, so its "original" for a multi-edit file was
the file *after* nine of the ten edits — restoring it left nine fields reverted, and I noticed
only because a follow-up probe behaved impossibly. The harness now groups edits per file, writes
once, and asserts a SHA-256 match on restore; all eight rows in the table above were produced by
the corrected version, and `make check` was re-run green afterwards. Recording it because "the
tool that verifies the fix was itself wrong" is the kind of thing that should not be discovered
by the next reviewer.

**Fourth: `auth → envelope` is a new dependency direction**, taken to avoid a second copy of
`parse_instant`. Defensible, and a real architectural cost that a reviewer may want spent
differently.

**Fifth: the first call to `strip_invisible_characters` in a process now costs ~0.1 s** for the
Unicode walk. Cached per process and off the import path, measured at 0.096 s on this machine.
It is a real change to first-message latency and nothing in the repo has a budget for it.

**Sixth: I widened Part 1 past the field the finding named.** Nine of the ten reason parameters
were not in the work order. I judged that leaving them was the defect this round exists to stop
repeating; if the orchestrator disagrees, the ten-field change is one commit and one helper and
is trivially reversible to the single field.

---

## Execution record

`make check` green at every checkpoint and at the end: `ruff check`, `ruff format --check` (97
files), `mypy --strict` (71 source files), `pytest -q -m "not network"` **1,529 passed**,
`tools.guards` 7 clean, `rubric_status.py --check` **7 PASS / 106 NOT TESTED / 11 transitions** —
unchanged from the round-9 baseline in every column. No rubric row was edited, no row was added
to `RUBRIC_TRANSITIONS.md` or `FINDINGS_LEDGER.md`, and no criterion was promoted.

No personal mail content appears anywhere in this round's code, tests or fixtures. Every
sentence used as an attack payload is invented for this repository, and every one of them is a
sentence a reviewer already published in `docs/reviews/ROUND_09/R-SEC-DISC.md` or is written to
match its shape.
