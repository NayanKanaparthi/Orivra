# ROUND 17 — R-RETR review (refuse the unanswerable, answer the rest)

**Reviewer:** R-RETR, independent instance, 2026-09-04. Sole gating reviewer for round 17.
Verified by execution per `AGENT_LOOP.md` §4/§5/§5a. **Source, tests and docs untouched** — every
probe ran from `/tmp/rretr17/*.py` against the real tree; every planted defect ran in a scratch copy
at `/tmp/rretr17/tree` with `PYTHONPATH` set and `mailweave.__file__` **and** `tests.__file__`
asserted to resolve there and asserted *not* to resolve into `/root/mailweave`. Probe files are named
against every result below. Nothing in `/tmp/rretr15`, `/tmp/rretr16` or `/tmp/r17impl` was used to
build any of my sets; where I re-ran a prior instance's file I say so and label it a regression check.

## Environment

| Gate | Result (run twice, before and after all probing, identical both times) |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 153 files already formatted |
| `mypy --strict` | Success, 127 source files |
| `python -m tools.guards` | 7 guards clean (forbidden-import, generative-client, gmail-endpoint, ground-truth-isolation, scope-literal, unaudited-disk-write, unwrapped-http-client) |
| `pytest -q -m "not network"` | **2,248 passed**; re-counted independently via `--collect-only -q` summed per file = **2,248** |
| `tools/rubric_status.py --check` | criteria 113; **6 PASS / 0 FAIL / 0 BLOCKER / 107 NOT TESTED**, 11 transitions — as the work order requires |

`mailweave.__file__` → `/root/mailweave/server/src/mailweave/__init__.py`. Nothing under
`/root/mailweave` was written by this review except tool caches (`find -newermt` over the tree
returns only `.ruff_cache`, `.hypothesis`, `.pytest_cache`, `.mypy_cache` entries).

**Scratch-tree discipline.** `/tmp/rretr17/tree` is a full copy including `docs/`. Asserted green
(returncode 0 over the whole suite) before the first plant; `__pycache__` cleared before every run;
the source restored from the real tree between plants; every plant asserts its anchor count before
writing and asserts the file changed after, printing the before/after content hash. After the last
plant I diffed `server/` and `tests/` against the real tree: identical.

## Reachability rule I applied (§5a)

Unchanged in substance from rounds 15 and 16, and restated because it decides every classification
below. `LadderRunner`, `assemble` and `Envelope` have no MCP tool surface today; §5a exists to stop
findings against code that does not exist and to stop re-review of sealed modules, **not** to make
this round's own code inert. **A defect triggered by an ordinary query string reaching
`LadderRunner.run` + `assemble` is REACHABLE.** Every finding I raise is reachable; I mark none inert.
Where the *fix* belongs to another workstream I name it, and the finding stays open and blocking
here (§5a: "a deferred finding is blocking in the round it returns to").

---

## Priority 1 — the invariant, attacked

> *"A probe composed from a subset of a query's fragments searches the region the query named;
> omitting a negation widens within the region, omitting a mailbox scope moves to a narrower one."*

### Is the membership test vacuous? No — and I established that by planting both ways

`/tmp/rretr17/inv_plants.py`, `inv_plants2.py`. Six invariant violations planted one at a time into
`/tmp/rretr17/tree`, each run against **only**
`test_every_probe_the_ladder_composes_searches_the_region_the_query_named`:

| plant | what it breaks | against the invariant test alone | against the whole suite |
|---|---|---|---|
| **I1** `mailbox_scope_of` returns `()` — the derivation the test itself reads | emptied oracle | **CAUGHT** | — |
| **I2** decomposition drops the scope from every unit (R-RETR-019 back) | L1b | **CAUGHT** | — |
| **I3** L3 conjoins a narrowing location instead of replacing it (R-RETR-021 back) | L3 | **MISSED** | CAUGHT (`test_a_broadening_probe_…`) |
| **I4** L0 drops the scope from its branch probe | L0 | **CAUGHT** | — |
| **I5** a decomposition probe silently **narrows** into `in:inbox` | L1b | **MISSED** | CAUGHT (`test_a_mailbox_scope_fragment_…`) |
| **I6** L2 strips the scope while declaring a *different* drop | L2 | **CAUGHT** | — |

**I1 is the important one.** Emptying `mailbox_scope_of` empties the `for fragment in wrote` loop, so
that half of the test goes vacuous — and the test still fails, on
`assert probe.include_spam_trash == widened_query`, which is derived from
`widens_beyond_the_default_mailbox` in `constants` rather than from the function under test. The test
has a second, independent oracle. That is the property round 12's emptied sweep did not have, and it
is real. I confirm the anti-vacuity claim.

### Are the two exemptions real exemptions, or holes? One of each

**The L2 exemption is a real exemption.** It is keyed on the probe's own *declared* drop
(`probe.rung is RungId.L2 and "in" in probe.dropped`), so a relaxation that strips the scope while
declaring something else is not waved through — I6 CAUGHT.

**The L3 exemption is a hole.** It is
`if probe.rung is RungId.L3 and probe.query.startswith(ANYWHERE_OPERATOR): assert
probe.include_spam_trash; continue`. Any L3 probe whose `q` *begins with* the widening operator is
waved through entirely — the invariant's own words, "replaces it **wholesale**", are not checked.
R-RETR-021's exact defect, planted back (**I3**), leaves the invariant test green. The suite catches
it elsewhere, so nothing is broken today; what is false is the account: the invariant is **not**
"enforced by one membership test over `LADDER`", and the finding it is said to subsume (R-RETR-021)
is in fact held by a different test. The live `label:` residue the implementer names in §9 is
precisely this shape (`in:anywhere label:projecta from:x` — declares a widening, restricts to a
label) and the invariant test is green on it. **R-RETR-031.**

**And the invariant does not constrain narrowing at all.** I5 — a probe that adds `in:inbox` where
the query named no location — is invariant-clean: `wrote` is empty, and `include_spam_trash` is
`False == False`. The statement says "searches the region the query named"; the enforcement says
"carries every *widening* scope fragment the query wrote, and agrees about `includeSpamTrash`".

### The region-widening the invariant permits that a user would call a leak — the thirteenth instance

The asymmetry table is stated over three classes, and the first is wrong for one member of it:

> a negation (`-cutover`, `-from:x`) — the probe matches a **superset within the same region**:
> precision only — **permitted**.

`-in:spam` and `-in:trash` are negations. Omitting them does **not** widen within the region: it
crosses the one boundary this entire round is about. `mailbox_scope_of` says so out loud —
*"A negated scope fragment … is not carried: it excludes, and omitting an exclusion widens rather
than narrows, which is the direction a decomposition probe is allowed to be wrong in."* It is not.

Executed, `/tmp/rretr17/p9_negscope.py` and `p11_negscope_l1b.py`:

```
mailweave_search('-in:spam -in:trash borogrove')
  wire     [('-in:spam -in:trash borogrove', False), ('borogrove', False),
            ('in:anywhere borogrove', True)]           <-- L3, includeSpamTrash=true
  sources  t-sp  q-2  role: matched   (a SPAM message)
           t-tr  q-3  role: matched   (a TRASH message)
  outcome  answered

mailweave_search('in:anywhere -in:spam zephyr borogrove')      # both words only in SPAM
  wire     [('in:anywhere -in:spam zephyr borogrove', True),
            ('in:anywhere zephyr', True), ('in:anywhere borogrove', True)]   <-- L1b, exclusion gone
  sources  t-sp  z-1, z-2  role: matched   (both SPAM)
  outcome  answered
```

The user wrote "everywhere **except** spam" and MailWeave returned, as matches, exactly the messages
the query excluded. The constraint drop *is* declared (`asked_for.dropped` names `in`,
`term_coverage 0.5`), so this is not round 15's silent blocker — but it is the exit condition's other
half, "No query reads outside what it asked for", failing on an ordinary Gmail idiom. **R-RETR-026.**

### My own plan-layer sweep — 5,979 queries, 29,720 planned probes

`/tmp/rretr17/s1_sweep.py`, over a 51-token vocabulary of my own (every shape this round changed,
plus negated scope, narrowing locations, `label:`, grouping, vacuous tokens, unproven operators):
every single, **every ordered pair**, and a strided walk over ordered triples.

```
swept                      5979
probes                     29720
parse_raised                  0
plan_raised                   0
lost_region                   0     <- the implementer's own rule, independently reproduced
flag_disagrees                0     <- include_spam_trash vs the query, independently reproduced
l3_did_not_widen              0
entered_excluded_region     201     <- my rule: a probe entered a region the query EXCLUDED
                                       by rung: L3 196, L0 5
```

The three checks the implementer reports as `0` reproduce as `0` on a set they did not build. The
fourth check is mine and is R-RETR-026. The five L0 cases are contradictory queries
(`in:trash -in:spam rfc822msgid:<…>` → L0 probes `in:trash rfc822msgid:<…>`, carrying one fragment
of the `in` constraint and dropping the other).

---

## Priority 2 — `matchable_content_of`, the blocker's structural fix

### What holds

`/tmp/rretr17/p4_matchable.py`, 44 hand-built shapes. Every reported spelling and every one I
invented in the *operator* family is correctly content-free: `subject:`, `label:`, `is:`, `in:`,
`has:`, `rfc822msgid:`, `newer_than:`, `larger:`, `subject:""`, `label:""`, `subject:<ZWSP>`,
`(subject:)`, fullwidth `Ｓｕｂｊｅｃｔ：`, `""`, `" "`, `""""`, `"\t"`, `"\xa0"`, `-""`, `"`, `"""`,
`{}`, `()`, U+200B, U+200F, U+061C, and the whitespace family. **The claim that it holds for an
operator nobody has enumerated is true and is structural**: the function strips any unquoted
`name:` prefix without consulting `OperatorName`, so any operator added tomorrow "either carries a
value or carries nothing" by construction. I could not falsify that half.

Unusual value syntax survives correctly: `larger:5M`, `size:1000000`, `filename:*.pdf`,
`rfc822msgid:<a@b.invalid>`, `list:x@parts.example`, `from:"Amy: Smith"`, `-subject:"a: b"`.
Nested and unbalanced quotes behave: `"a "b" c"` → `a "b" c`; `"unbalanced` → `unbalanced`.

### Where the "structural, not enumerated" claim is false — the dangerous direction

The docstring says the content test is *"a structural question … what, once everything that is not
content is removed, is left for Gmail to match?"* and that a token's content is empty **iff** it names
nothing. What it actually removes is **one Unicode general category, `Cf`**. Every other
blank-rendering code point is content:

| token | `matchable_content_of` | `selects_something` | reaches Gmail as |
|---|---|---|---|
| U+3164 HANGUL FILLER `ㅤ` | `'ᅠ'` (NFKC → U+1160, category Lo) | **True** | `('ᅠ', False)` then **`('in:anywhere ᅠ', True)`** |
| U+2800 BRAILLE PATTERN BLANK | `'⠀'` (So) | **True** | — (filtered later by the term pipeline) |
| U+0301 lone combining acute | `'́'` (Mn) | **True** | — |
| U+FE0F VARIATION SELECTOR-16 | `'️'` (Mn) | **True** | — |

`/tmp/rretr17/p5_blank_wire.py`, `p6_blank_combo.py`:

```
mailweave_search('ㅤ')          wire [('ᅠ', False), ('in:anywhere ᅠ', True)]     term_coverage 1.0
mailweave_search('-zephyr ㅤ')  wire [('-zephyr ᅠ', False), ('in:anywhere -zephyr ᅠ', True)]
mailweave_search('subject:ㅤ')  wire [('subject:ㅤ', False), ('in:anywhere subject:ㅤ', True)]
```

That is R-RETR-017's wire shape exactly — a fragment that cannot narrow, widened to the whole
mailbox with `includeSpamTrash=true` — reached through a spelling the "structural" predicate does not
cover, including through the `-cutover` disguise the round-16 half was written for. Whether Gmail
answers `q='ᅠ'` with the whole mailbox I cannot establish here (**R-GMAIL**); the double treats it as
a literal and matches nothing, which is why `|H| = 0` above. The *claim* is false either way, and the
fix that was required to stop being an enumeration is one category wider than the one it replaced.
**R-RETR-029.**

### The other direction (says nothing, would select something) — found, and benign

`cutover:`, `TODO:`, `urgent:` are content-free by this rule (unquoted head, empty tail). All three
are also `UNKNOWN_OPERATOR` at the tokeniser, so they are dropped-and-declared either way — the
declaration reason differs (`selects_nothing` rather than `unproven_operator`), the outcome does not.
Fullwidth `Ｓｕｂｊｅｃｔ：` is content-free here while `tokenise` (which does no NFKC) reads it as a
term; the conservative direction. I found no case in this direction that costs a row.

---

## Priority 3 — the report-versus-raise line, and ROUTE-01

### The line holds, and I could not break it

`/tmp/rretr17/p20_fuzz.py`: 338 inputs — NUL bytes, CR/LF, ANSI escapes, 4,000-character terms,
50 and 51 consecutive quotes, 40 nested parens, RLO/tatweel/ZWJ, astral text, `a: ` × 200,
`in:anywhere` × 30, five repeated `subject:` operators, 300 random strings over an alphabet that
includes ZWSP, HANGUL FILLER, soft hyphen and fullwidth colon.

```
inputs 338   envelopes 335   QueryNotSearchable 3   other exceptions 0
every raise was a whitespace-only input; no non-empty input raised
```

`/tmp/rretr17/p12_report.py`, `p13_report2.py`: the report class carries, for every shape I tried
(`""`, `" "`, `subject:`, `label:`, `is:`, `in:`, `has:`, `subject:""`, `label:""`, `the and of`,
`?`, `!!!`, `(a OR b)`, `{a b}`, `thread:1837abf`, `tel:…`, `in:anywhere`, `in:spam`, `in:trash`,
`in:anywhere -zephyr`, U+200B): **zero Gmail calls**, `rungs: ()`, all five rungs in `not_tried`
under `not_applicable`, an `empty_diagnosis`, `outcome: inconclusive` (never `not_found`, OD-2),
`sufficiency: insufficient`, `term_coverage: 0.0`, and every `dropped_declarations` pair present in
`asked_for.dropped` with a non-empty `why`.

### Is any *report* fabricating fields? I checked the implementer's own justification rather than trusting it

The account says the empty query must raise because its report would read `term_coverage: 1.0` and
`empty_diagnosis: complete`. **True on execution** (`/tmp/rretr17/p13_report2.py`):
`analyse('').carries_nothing_searchable` is `False` — the guard is `not self.constraints and
bool(self.raw.strip())` — so `term_coverage(())` returns **1.0**, while `analyse('""')` has
`carries_nothing_searchable True` and returns **0.0**. The distinction the line rests on is real and
is a property of the input, exactly as claimed.

The one field I would call weak is `empty_diagnosis: complete` on a run where **no rung executed and
no drop was probed** (`""`, `the and of`, `?`, `thread:1837abf`). It is vacuously true — there are no
constraints, so no drop went untried — but it is the same "a rung that never executed probed nothing
at all" shape `untried_drops`' own docstring names as ADV-105's defect coming back through the other
door. It is not a fabrication in the way `term_coverage 1.0` would be (the response as a whole reads
`0.0` / `inconclusive` / `insufficient`), and the implementer already records the missing third
`EmptyDiagnosisStatus` member as **WS-10**. I confirm that residue and do not raise it separately.

### The one thing missing from the report, and it is ROUTE-01's own list

ROUTE-01's acceptance enumerates five things a zero-evidence response must carry: queries executed,
constraints dropped with reasons, per-rung hit counts, what was not tried, **and affordances**. Over
every zero-evidence response I produced — the report class, and ordinary zero-hit runs such as
`borogrove` — `envelope.affordances` is `[]`, `empty_diagnosis.affordance` is `None`, and there is no
`withheld` or `scan_scope` affordance either. Affordances *are* minted where the code has one to mint
(a restoring drop; a budget-bound untried drop, verified at k=9 → `{"relax": {"max_probes": 9}}`), and
minting a boilerplate one where nothing would help is precisely what R-RETR-023's fix removed this
round — so the gap is not "always mint something". It is that for the class this round created there
**are** concrete calls that would reach a rung and none is offered: `thread:1837abf` → search
`"1837abf"` as a quoted term; `(zephyr OR borogrove)` → search `zephyr borogrove`. AD-03 requires an
affordance to be a call that would reach the untried rung; these exist and are not offered.
**R-RETR-032**, and it is why I do not recommend restoring ROUTE-01 this round. See the
recommendations.

---

## Priority 4 — should L3's published broadening reach spam and trash at all? A reasoned verdict

**The facts, established.** With no scope named, `BroadeningRung._anywhere` composes
`in:anywhere <text constraints>` and `Probe.include_spam_trash` is `True`. It runs only when
`_should_run` sees `evidence_count == 0` — nothing was found by L0, L1 or L1b's intersection. It is
declared in `scan_scope` as its `q` (`ScanScopeEntry` has no `include_spam_trash` field; the reader
infers the flag from the operator inside the string). Rows it admits are disclosed as `role: matched`
with `reason: "gmail q matched at L3: in:anywhere borogrove"` and `outcome: answered`.

**Declaring the probe is not the same as declaring the row, and that is the gap.** I dumped the wire
form (`/tmp/rretr17`, `model_dump(mode="json")` on the `-in:spam borogrove` case): a `MessageRow`
carries `id`, `position`, `internal_date`, `role`, `reason`, `constraint_coverage`, `depth`,
`reductions`, `unabridged`, `content`. **There is no field that says this message is in SPAM or
TRASH.** A calling agent receiving `outcome: answered` and a `matched` row has, as its only signal,
the substring `in:anywhere` inside `reason`, from which it can infer that the row *might* be from
spam or trash and nothing more. The declaration lives at the query level; the disclosure lives at the
row level; the two are not joined.

**My verdict, as a product question.**

1. **When the caller named no scope, L3 reaching spam and trash is defensible and I would keep it.**
   It fires only after the default mailbox has returned nothing; A.7 L3's published step is literally
   `in:anywhere`; spam and trash are the caller's own mailbox, not a third party's; and the
   alternative — "we found nothing" over a message sitting in the caller's spam folder — is the
   false-negative this project exists to remove. Round 15's blocker was not that L3 read spam; it was
   that a query whose content was never executed was answered with a mailbox read and called
   `answered` at `term_coverage 1.0`. That specific defect is closed.
2. **It is not enough as it stands, for one concrete reason**: a row admitted from spam or trash is
   indistinguishable, in the payload, from a row admitted from the inbox. The smallest honest
   repair is not to stop the probe but to mark the row — a region marker on the row, or a
   `reductions`/`scan_scope` join that says which rows came from the widened region. I am not filing
   that as a finding against this round (it is a D.2 schema addition, **WS-10/WS-11**, and outside
   the round's diff), but I record it as the thing that would make "declared" true at the level the
   user experiences.
3. **When the caller *excluded* spam or trash, reaching it is not defensible at all**, and that is a
   finding rather than a product question: R-RETR-026. `-in:spam` is the caller saying, in Gmail's
   own vocabulary, "not there". A broadening step that discards it has not broadened the caller's
   question; it has answered a different one.
4. **When the caller named a narrowing region** (`in:inbox`, `label:work`), L3 replaces or drops it
   and reaches spam and trash. `in:inbox borogrove` → `in:anywhere borogrove`, drop declared;
   `label:projecta borogrove` → `in:anywhere borogrove`, the label silently absent from the probe's
   own `enforced`/`dropped` (the response-level drop is recovered by `_asked_for`'s fallback). I
   judge this inside A.7 L3's published step and adequately declared, but note the arbitrariness:
   whether a `label:` constraint survives L3 depends on whether the query also has a bare term
   (`label:projecta from:x` → `in:anywhere label:projecta from:x`; `label:projecta borogrove` →
   `in:anywhere borogrove`).

**Does this need an owner decision?** For (1) and (2), yes — one decision, narrow: *may a broadening
step disclose a spam or trash message as `matched`, and if so must the row say so?* It is OD-2's
neighbour and belongs with OD-4 (personal-mailbox forensics). For (3), no: it is a defect, and the
fix is in this round's code.

---

## Priority 5 — recall, adversarially, on my own sets

### My plausible-query audit — 58 queries, 16 categories, my own mailbox (`/tmp/rretr17/s2_plausible.py`)

```
queries              58
RAISED                0
CRASH                 1      (in the test double, not the product — see R-RETR-033)
envelope, no Gmail    7
reached Gmail        50
outcome              answered 40, inconclusive 17
probes into spam/trash the query did not ask for: 11   (all L3's published step)
```

**The "before" column is measured, not remembered** (`/tmp/rretr17/p24_before_audit.py`): the
round-16 tree no longer exists, so I reconstructed it in my scratch tree by planting the inverse of
every round-17 change that can alter whether a query gets an envelope at all (P1, P3, P4, P10, P11),
each anchor asserted `1/1`, each file asserted changed, imports asserted inside the scratch tree. On
the same 58 queries:

```
                       round 16 (reconstructed)   round 17
raised, no envelope             8                      0
envelope with no Gmail call     0                      7
reached Gmail                  49                     50
outcome: answered              40                     40
```

The eight are the five colon-carrying phrases, the two grouping shapes and `thread:1837abf`. The
vacuous family (`""`, `" "`, `subject:`, `subject:""`) did **not** raise under round 16 — it reached
Gmail, which is R-RETR-017. No query round 16 answered is refused now, and the seven no-Gmail-call
reports are the eight refusals minus the five phrases (now searched) plus the four vacuous shapes
(which round 16 answered by reading the mailbox).

Every quoted phrase with a colon now works end to end: `"Re: quadrant notice"`, `"9:30 standup"`,
`"note: see below"`, `"3:2"`, `"http://parts.invalid/x"` — all reach Gmail as phrase searches with
`term_coverage 1.0`. R-RETR-018 is closed and I reproduce that independently.

### Constructed recovery cases — 21/22 (`/tmp/rretr17/s4_recall.py`)

My own cases, my own mailboxes, the answer planted in a known thread with eleven noise threads. **This
is a constructed-case measurement and not a recall rate**; LEX-03's and ROUTE-02's bars are
`[UNSET — register at G0]` against corpora that do not exist.

Recovered: the founding shape in the inbox, in spam, in trash and under `in:anywhere` (the round's
Part 3, confirmed on my own fixtures); 3, 4, 5 and 6 bare words split one-per-message; two and four
operators plus two split terms; three contradictory-operator shapes (`in:spam in:inbox`,
`from:x -from:x`, `after: > before:`); five phrases containing operator-like tokens; an accented
term; a term beside a soft-hyphen token; a term with an empty phrase pasted in.

**The A.7 cap's precision cost — R-RETR-024's unclosed half — is now declared and I confirm it.** At
4, 5 and 6 units the thread is still recovered and the response reports `enforced: ()`,
`term_coverage: 0.0`; at 3 units it reports `enforced: ('terms',)`, `1.0`. The claim now falls when
the cap binds, which is what the finding asked for.

**Not recovered: `ＩＮ：ＡＮＹＷＨＥＲＥ zephyr`.** The fullwidth widening operator is not
NFKC-normalised by `tokenise`, so it becomes a term; the term pipeline then strips `in:` as a
stopword and searches for the word **`anywhere`**. The scope the caller asked for is lost, a term they
did not write is added, and the response reports
`enforced: ('terms', 'stopwords_removed:in:anywhere')`. `constants._operator_token` *does* normalise
it — so `constants` and `tokenise` disagree about the same token. Pre-existing, not this round's diff,
and it is the third module in this repository to disagree about NFKC. **R-RETR-034.**

### Where recall is lost by design, and declared

`ratio 3:2` executes as `ratio` (`3:2` is an unproven operator, declared). `http://parts.invalid/x`
unquoted is an unproven operator; quoted it works. `zephyr.` is sent verbatim with the trailing
period. All three are declared and all three are the implementer's own open A.6 normalisation items.

---

## Priority 6 — evidence preservation across every new path

`/tmp/rretr17/s3_preserve.py`, **600 randomised trials**, mailboxes of 1–40 messages over random
threads, senders, label sets (INBOX/UNREAD/SPAM/TRASH/IMPORTANT/PROJECTA), attachments and rfc822
ids, against 30 query shapes covering every path this round added — `selects_nothing` filtering, the
report-not-raise path, the new `enforced` union, L3 replacement, scoped and negated-scope
decomposition, the repeated-fragment de-duplication, and the quoted-colon phrase.

```
trials 600   envelopes 600   refusals 0   crashes 0
H subset of (disclosed union withheld)          : 0 violations
disclosed and withheld disjoint                 : 0 violations
no phantom id                                   : 0 violations
reads outside what the query asked for          : 0     (the implementer's rule, reproduced)
disclosed a row from a region the query EXCLUDED: 47     (mine — R-RETR-026)
```

The first run of this harness never produced a `withheld` record, so the disposition half was
untested. I ran a second, dedicated pass with 20–45-message mailboxes over 20–45 threads to force
`max_hit_threads = 12` overflow: **120 trials, 45 of them carrying at least one withheld record,
0 violations of `H = disclosed ∪ withheld`, 0 overlaps.** I state that separately because the
implementer's own 400-trial preservation claim gives no evidence that its mailboxes ever exceeded the
cap, and a preservation invariant that never sees a withheld record is a weaker statement than it
reads as.

---

## Priority 7 — the reintroduction checks

**The harness tests the scratch tree.** `/tmp/r17impl/plant.py::assert_imports_resolve_into_the_
scratch_tree` runs a subprocess with `PYTHONPATH` set and asserts both `mailweave.__file__` and
`tests.__file__` start with `/tmp/r17impl/tree/` **and** do not start with `/root/mailweave/`. I ran
it: it passes and prints the two scratch paths. Both prior instances found this trap; this round did
not fall into it.

**All sixteen plants re-derived and re-run in my own tree, against the whole suite** (not only the
test each names): `/tmp/rretr17/p15_replants.py`, `plant.py`. **16/16 CAUGHT**, every anchor `1/1`,
every file changed, and in each case the failing test is the one the plant names:

```
P1 -> test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_unknown_operator
P2 -> test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled
P3 -> test_no_rung_plans_a_probe_for_a_query_the_parser_produced_nothing_from[""]
P4 -> test_a_token_that_names_nothing_to_match_is_not_a_probe_however_it_is_spelled
P5 -> test_every_probe_the_ladder_composes_searches_the_region_the_query_named
P6 -> test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to
P7 -> test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_widens_to
P8 -> test_a_route_that_widened_a_constraint_does_not_report_it_enforced
P9 -> test_a_query_that_names_only_where_to_look_is_reported_not_scanned[in:anywhere]
P10-> test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned[(rollout OR escalation)]
P11-> test_a_query_the_parser_produces_nothing_from_is_reported_not_scanned[(rollout OR escalation)]
P12-> test_a_drop_no_budget_can_reach_is_not_offered_a_budget
P13-> test_a_repeated_identical_fragment_is_one_unit_and_every_label_is_unique
P14-> test_a_probe_whose_rows_an_earlier_probe_admitted_still_counts_as_a_route
P15-> test_a_decomposition_that_never_intersected_does_not_report_the_query_enforced
P16-> test_every_probe_the_ladder_composes_searches_the_region_the_query_named
```

**The P2 "MISSED on first run" disclosure is true, and I verified it the way it was written**
(`/tmp/rretr17/p14_p2.py`). Planting P2 against its own test: **CAUGHT**. Planting the *same* defect
against the whole suite with that one test deselected: **MISSED — 2,248 tests green with the clause
removed.** The recorded statement ("the clause has no reachable trigger today, because the parse
layer removes vacuous tokens first, and it is executed directly rather than left as a claim") is
exactly what execution shows. That is honest disclosure and it was worth confirming.

**Two of my own plants, to test whether the defects I found are pinned by anything**
(`/tmp/rretr17/p18_freeplants.py`, `p19_fixcheck.py`):

* **N1** — L0's A.8a E-c branch stops claiming the whole `terms` constraint: **MISSED**, the whole
  suite is green with the honest value. Nothing asserts the over-claim I raise as R-RETR-028.
* **N3** — L3's widening probe carries the caller's negated scope fragments through: **MISSED**,
  the whole suite is green, and the plan-layer effect is what R-RETR-026 needs
  (`-in:spam borogrove` → `in:anywhere borogrove -in:spam`, `-in:spam -in:trash zephyr` →
  `in:anywhere zephyr -in:spam -in:trash`). The fix is unasserted and free at L3; the L1b half needs
  `mailbox_scope_of` as well.
* **N2** — `enforced` as the **intersection** over routes instead of the union: **CAUGHT**
  (`test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint`). So the blunt fix for
  R-RETR-030 is wrong and the required fix has to be narrower; I say which in the finding.

---

## Findings

```
ID:            R-RETR-026
Severity:      HIGH
Reachability:  REACHABLE today. An ordinary Gmail idiom (`-in:spam`) through
               LadderRunner.run + assemble, both of which exist and execute. The wire
               shape and the disclosure follow from the code whatever Gmail returns.
Rubric:        The work order's exit condition ("No query reads outside what it asked
               for"); LEX-02 (a signal enforced-inverted rather than enforced or
               dropped); EV-04's paired hallucinated-found guard; AD A.7 L3; contract I-4.
Location:      server/src/mailweave/retrieval/ladder.py, BroadeningRung._anywhere
                 (`chosen` keeps only text-kind constraints, so a negated `in:` fragment
                 is dropped and `in:anywhere` is composed over the remainder);
               server/src/mailweave/query/analysis.py, mailbox_scope_of (a negated scope
                 fragment is deliberately not carried, so L1b's units lose it too);
               server/src/mailweave/query/analysis.py, decomposition_units_of — the
                 invariant's own asymmetry table, whose "a negation may be left out,
                 because the probe matches a superset within the same region" is false
                 for `-in:spam` / `-in:trash`
Repro:         /tmp/rretr17/p9_negscope.py, p11_negscope_l1b.py, s1_sweep.py, s3_preserve.py
                 mailweave_search('-in:spam -in:trash borogrove')
                   -> wire [('-in:spam -in:trash borogrove', False), ('borogrove', False),
                            ('in:anywhere borogrove', True)]
                 mailweave_search('in:anywhere -in:spam zephyr borogrove')
                   -> L1b wire ('in:anywhere zephyr', True), ('in:anywhere borogrove', True)
                 5,979-query plan sweep: 201 probes enter a region the query excluded
                   (L3 196, L0 5); 600 randomised end-to-end trials: 47 disclose such a row
Expected:      A fragment that says "not in this region" constrains the region exactly as a
               positive one does. The invariant's rule — only the rung whose published step
               is to replace the region may change it, and it replaces wholesale and
               declares it — must treat `-in:spam` as a region fragment, not as an ordinary
               negation. No probe may set includeSpamTrash=true over a query that excluded
               spam or trash without carrying the exclusion.
Actual:        `mailweave_search('-in:spam -in:trash borogrove')` discloses a SPAM message
               and a TRASH message as `role: matched` under `outcome: answered`, admitted by
               `in:anywhere borogrove` with includeSpamTrash=true. `in:anywhere -in:spam
               zephyr borogrove` does the same at L1b, on messages that exist only in spam.
               The drop is declared (`asked_for.dropped` names `in`, term_coverage 0.5), so
               the response does not lie about it — but it returns, as matches, precisely the
               messages the query excluded.
Required fix:  Two edits, one statement. (1) `mailbox_scope_of` (or a sibling derivation
               beside it) must yield the query's negated mailbox-scope fragments as well, so
               `decomposition_units_of` and `ExactOperatorRung._in_scope` carry them onto
               every composed probe. (2) `BroadeningRung._anywhere` must carry every negated
               mailbox-scope fragment into the widened `q` regardless of the constraint kind
               `chosen` selected — verified as a plan-layer fix in /tmp/rretr17/p19_fixcheck.py,
               and the whole suite is green with it (plant N3), so nothing asserts the current
               behaviour. Restate the invariant's asymmetry table so "a negation may be left
               out" excludes a negated region fragment, and extend
               `test_every_probe_the_ladder_composes_searches_the_region_the_query_named` to
               assert it — the test as written cannot see this because `wrote` is the positive
               scope only.
```
```
ID:            R-RETR-027
Severity:      HIGH
Reachability:  REACHABLE today. `-"some phrase"` is ordinary Gmail syntax and reaches
               `analyse` from any query string.
Rubric:        LEX-02 ("Parsed query signals are either enforced in the executed `q` or
               reported as dropped"; "cases where a signal was silently dropped: 0");
               EV-04's paired hallucinated-found guard; contract I-4.
Location:      server/src/mailweave/query/analysis.py, analyse
                 (`phrases = tuple(token.value for token in matchable if token.role is
                 TokenRole.PHRASE)` — `token.negated` is discarded);
               server/src/mailweave/query/analysis.py, _build_constraints
                 (the phrase constraint renders `f'"{phrase}"'`, with no negation prefix);
               server/src/mailweave/query/operators.py, tokenise — round 17's Part-2 clause
                 is what newly routes a *colon-carrying* negated phrase into this path;
               tests/test_query_analysis.py:769, which asserts only
                 `parse('-"Re: quarterly plan"').phrases == ("Re: quarterly plan",)`
Repro:         /tmp/rretr17/p21_lex.py, p22_negphrase.py, p23_before.py
                 mailweave_search('-"quadrant notice zephyr"')
                   -> render '"quadrant notice zephyr"'   wire [('"quadrant notice zephyr"', False)]
                   -> the one message that DOES contain the phrase: role matched,
                      constraint_coverage ('phrase',), enforced ('phrase',),
                      term_coverage 1.0, outcome answered
                 Before/after, measured by planting round 17's Part-2 clause out:
                   round 16:  '-"Re: quadrant" zephyr' -> render 'zephyr',
                              unproven ('-"Re: quadrant"',)          [dropped and declared]
                   round 17:  '-"Re: quadrant" zephyr' -> render '"Re: quadrant" zephyr'
                                                                    [executed, inverted]
                   both:      '-"quadrant notice" zephyr' -> render '"quadrant notice" zephyr'
Expected:      A negated phrase is a phrase to exclude. Either the negation is carried into
               the executed `q` (`-"…"`), or the constraint is declared dropped. Executing
               the exact opposite of a written constraint and reporting it `enforced` is the
               silent-drop LEX-02 counts at zero tolerance, made worse by being an inversion
               rather than an omission.
Actual:        Polarity is discarded at the parse. The response reports `enforced:
               ('phrase',)`, `dropped: []`, `term_coverage: 1.0`, `outcome: answered`, and
               each disclosed row carries `constraint_coverage: ('phrase',)` — the claim
               "this message satisfied the phrase constraint you wrote", for a message that
               satisfies its negation. Pre-existing for a colon-free negated phrase;
               **newly reached this round** for a colon-carrying one, which round 16 dropped
               and declared. The round's own test for this shape asserts the half that
               works.
Required fix:  Carry polarity on the phrase constraint — `ParsedQuery.phrases` (or a parallel
               structure) must record `negated`, `_build_constraints` must render `-"…"` for
               a negated phrase, and `qualifying_phrases` must exclude negated phrases from
               A.8a branch E-b (an exclusion is not an exact-signal lookup). Assert the
               polarity in `test_a_quoted_phrase_containing_a_colon_is_a_phrase_not_an_
               unknown_operator`, where the negated phrase is already a case.
```
```
ID:            R-RETR-028
Severity:      HIGH
Reachability:  REACHABLE today. An identifier or a long quoted phrase beside any other
               term, through LadderRunner.run + assemble.
Rubric:        LEX-02 (`asked_for` and `constraint_coverage` correctness); LEX-04 (the stop
               is reached through it, though the defect is not the stop's); EV-04's paired
               hallucinated-found guard; AD A.8a branches E-b/E-c; AD D.3 rule 1b.
Location:      server/src/mailweave/retrieval/ladder.py, ExactOperatorRung.plan —
                 the E-c branch reports `enforced=(TERMS_CONSTRAINT, *scope_names)` for a
                 probe whose `q` is one quoted identifier token, and the E-b branch reports
                 `enforced=("phrase", *scope_names)` for a probe carrying the first
                 qualifying phrase only;
               server/src/mailweave/retrieval/assemble.py, _asked_for — the route's
                 `enforced` is taken whole, with no equivalent of
                 `_decomposition_enforced`'s "every piece of this constraint was probed"
Repro:         /tmp/rretr17/p3_l0ident.py and the two-phrase case in the same directory
                 mailweave_search('PO-2026-0041 zephyr')
                   wire      [('"PO-2026-0041"', False)]        stop D.3-1b, ladder halts
                   rows      i-1 role matched, constraint_coverage ('terms',)
                             — i-1 does not contain "zephyr"; a different thread does
                   response  enforced ('terms',)  dropped []  term_coverage 1.0
                             outcome answered   sufficiency sufficient
                 mailweave_search('"quadrant notice zephyr" "grommet widget log"')
                   wire      [('"quadrant notice zephyr"', False)]      stop D.3-1b
                   rows      h1 role matched, constraint_coverage ('phrase',)
                             — h1 contains the first phrase only
                   response  enforced ('phrase',)  dropped []  term_coverage 1.0
Expected:      The rule Part 4 established for L1b and L3 — a constraint is enforced only by
               a route that carried it whole — applies to L0. A branch that executes one
               fragment of a multi-fragment constraint has not enforced that constraint, and
               a row it admitted has not satisfied it.
Actual:        L0 claims the whole constraint from one fragment of it, at both branches. The
               ladder then halts under D.3 rule 1b, so no later rung can correct the claim,
               and the response reports `term_coverage 1.0`, `constraint_drop_depth 0` and
               `sufficiency: sufficient` over a row that satisfies part of the query. This is
               R-RETR-020's own class at the one rung Part 4 did not reach.
Required fix:  Give the L0 probe an `enforced` that names a constraint only when the branch
               fragment is the whole of it — the E-c branch names `terms` only when the
               identifier is the query's only search term; the E-b branch names `phrase` only
               when the query wrote one qualifying phrase and no other phrase — and otherwise
               names nothing, letting `_asked_for`'s drop path report it with L0 beside it.
               Nothing in the suite asserts the present value (plant N1: the honest value
               leaves 2,248 tests green), so the fix is unconstrained by existing tests and
               must arrive with its own.
```
```
ID:            R-RETR-029
Severity:      MEDIUM
Reachability:  REACHABLE today for the wire shape (established); the disclosure consequence
               depends on how Gmail evaluates a blank-rendering token, which is a live
               measurement (R-GMAIL).
Rubric:        LEX-02; AD A.7 L3; the work order's Part 1 requirement that the predicate
               "must hold for fragments nobody has enumerated".
Location:      server/src/mailweave/constants.py, matchable_content_of — the content filter
                 is `unicodedata.category(character) != FORMAT_CHARACTER_CATEGORY`, i.e.
                 exactly one Unicode general category (`Cf`), described in its own docstring
                 as "a structural question" that holds "for spellings nobody has written
                 down"
Repro:         /tmp/rretr17/p4_matchable.py, p5_blank_wire.py, p6_blank_combo.py
                 matchable_content_of('ㅤ') == 'ᅠ'   (NFKC, category Lo)
                 matchable_content_of('⠀') == '⠀'   (category So)
                 matchable_content_of('́') == '́'   (category Mn)
                 mailweave_search('ㅤ')
                   -> wire [('ᅠ', False), ('in:anywhere ᅠ', True)]
                 mailweave_search('-zephyr ㅤ')
                   -> wire [('-zephyr ᅠ', False), ('in:anywhere -zephyr ᅠ', True)]
                 mailweave_search('subject:ㅤ')
                   -> wire [('subject:ㅤ', False), ('in:anywhere subject:ㅤ', True)]
Expected:      The predicate that replaced round 16's enumeration must not itself be an
               enumeration. A token that renders as nothing and asks Gmail to match nothing
               must not become a constraint, must not be a decomposition unit, and must not
               be composed beside the widening operator with includeSpamTrash=true — the
               shape `Probe.__post_init__` exists to make unrepresentable.
Actual:        `matchable_content_of` removes one Unicode category. U+3164 HANGUL FILLER,
               U+2800 BRAILLE PATTERN BLANK, lone combining marks and variation selectors are
               all "content", so U+3164 becomes a `terms` constraint and L3 composes
               `in:anywhere ᅠ` with includeSpamTrash=true — R-RETR-017's exact wire
               shape, including through the `-cutover` disguise the round-16 half was written
               for. The double treats the token as a literal, so |H| = 0 there; if Gmail
               ignores it, the BLOCKER's disclosure returns unchanged.
Required fix:  State the property the docstring claims: content is what remains after
               removing everything with no rendered width. The nearest defensible structural
               test is to strip characters whose category is `Cf`, `Cc`, `Zs`, `Zl`, `Zp`,
               `Mn` and `Me` **and** the Unicode "Default_Ignorable_Code_Point" set, or —
               simpler and more honest — to require at least one character whose category
               starts with `L`, `N`, `P` or `S` *and* which is not Default_Ignorable. Whatever
               is chosen, derive it from the runtime as `FORMAT_CHARACTER_CATEGORY` already
               is, and execute it over a generated family rather than a list. Independently,
               record the Gmail half (does `q` = one filler character return the mailbox?)
               as an R-GMAIL question, because the severity of this finding is decided there.
```
```
ID:            R-RETR-030
Severity:      MEDIUM
Reachability:  REACHABLE today. Any query with two constraints where L1 finds one row and
               L1b's piece probes find others.
Rubric:        LEX-02 (`asked_for.enforced`, `term_coverage`); EV-04's paired
               hallucinated-found guard; ROUTE-01's "never a nonexistence claim" sibling —
               a claim about what was enforced, over rows no enforcing route admitted.
Location:      server/src/mailweave/retrieval/assemble.py, _asked_for —
                 `carried |= this_route` over `_routes(run)`, so `enforced` is the union over
                 alternative routes, and the fallback `frozenset(entry.probe.enforced)` for
                 an L1b probe when `decomposition_answered` is False credits a single-fragment
                 unit with its whole constraint
Repro:         /tmp/rretr17/p2_union.py, p8_leak2.py, p17_more.py
                 mailweave_search('in:inbox zephyr')  (e-arch is labelled IMPORTANT, not INBOX)
                   rows     e-in   matched  coverage ('in','terms')  reason 'in:inbox zephyr'
                            e-arch matched  coverage ('terms',)      reason 'zephyr'
                   response enforced ('in','terms')  dropped []  term_coverage 1.0
                            outcome answered
                 mailweave_search('label:projecta zephyr')  (l-2 carries no PROJECTA label)
                   response enforced ('label','terms')  term_coverage 1.0, l-2 disclosed matched
                 mailweave_search('newer_than:7d zephyr borogrove')  (both words in a Jan-2025 thread)
                   response enforced ('newer_than',)  term_coverage 0.5, two Jan-2025 rows matched
Expected:      `asked_for.enforced` and `term_coverage` are response-level statements. A
               constraint should be reported enforced only if every route that admitted a
               disclosed row carried it — otherwise the response asserts, of the disclosure as
               a whole, something true of only part of it.
Actual:        The union makes `enforced` the *most* generous claim available across
               alternative routes, and the rows the non-carrying route admitted are disclosed
               as `matched` under it. Per-row `constraint_coverage` is honest throughout, which
               is what keeps this at MEDIUM. The implementer names this residue in §9 as
               R-RETR-024's unclosed half and defers it to WS-10/WS-11 as a schema gap; I do
               not accept the schema framing — the schema already has the field, and the honest
               value is computable today.
Required fix:  Not the plain intersection: I planted it (`carried = carried & this_route`) and
               it fails `test_a_decomposition_probe_is_not_reported_as_a_dropped_constraint`,
               because L1b's siblings legitimately carry different pieces. The correct
               narrowing is to intersect over the routes that admitted a **disclosed** row —
               `_routes` already knows which probes returned rows, and `assemble` already
               computes the disclosure before `_asked_for` runs (its docstring says so and
               gives the reason). A constraint that some such route did not carry is a
               `DroppedConstraint` named with that route's rung, exactly as the L3-only case
               already is. If the orchestrator prefers to keep the union, then `term_coverage`
               must stop being derived from it, because the two together are what state the
               falsehood.
```
```
ID:            R-RETR-031
Severity:      MEDIUM
Reachability:  REACHABLE as a coverage defect today — the test exists and executes, and the
               shape it fails to constrain (a probe that declares a widening and restricts)
               is live in `label:` queries. No wrong row today; the guard is what is missing.
Rubric:        The work order's Part 3 ("state what the invariant is … and enforce it once");
               AL §7.2 (a test that passes for the wrong reason); LEX-03.
Location:      tests/test_lexical_ladder.py,
                 test_every_probe_the_ladder_composes_searches_the_region_the_query_named,
                 the L3 branch:
                   if probe.rung is RungId.L3 and probe.query.startswith(ANYWHERE_OPERATOR):
                       assert probe.include_spam_trash; continue
               and, for the narrowing half, the absence of any assertion about fragments the
               probe added that the query did not write
Repro:         /tmp/rretr17/inv_plants.py, inv_plants2.py
                 I3  `_anywhere` filters on is_the_widening_mailbox_operator instead of
                     names_a_mailbox_location — R-RETR-021 verbatim — and the invariant test
                     is GREEN. (The suite catches it in
                     test_a_broadening_probe_does_not_carry_a_narrower_scope_than_the_one_it_
                     widens_to.)
                 I5  every multi-fragment decomposition unit is prefixed with `in:inbox`, so a
                     probe searches a region the query never named — invariant test GREEN.
                     (Caught elsewhere.)
Expected:      "The invariant … is enforced once by one membership test over `LADDER` with two
               enumerated exemptions" (IMPLEMENTER §0, §3). If that sentence is true, the two
               findings it is said to subsume must both fail this test when planted back.
Actual:        R-RETR-021 does not fail it. The L3 exemption asks only that the `q` begins with
               the widening operator and that the flag is true; "replaces it wholesale" is not
               checked, so an L3 probe may carry any region restriction after the operator and
               pass. The live `label:` residue is exactly that shape. Separately, the invariant
               is stated as "searches the region the query named" and enforced as "carries every
               *widening* fragment the query wrote", so a probe that narrows into a region
               nobody named is invariant-clean.
Required fix:  In the L3 branch, replace `continue` with the positive assertion the sentence
               makes: no fragment of the probe's `q` may name a mailbox location other than the
               widening operator itself (`names_a_mailbox_location`), and no fragment may name a
               region the query did not write. Add the narrowing half to the general branch:
               every `in:` fragment of a probe's `q` must appear in the query's own render, for
               every rung. Then re-plant I3 and I5 against this test alone and require CAUGHT —
               the anti-vacuity block should assert that too, as it already asserts
               `len(LADDER) == 5` and `checked > 100`.
```
```
ID:            R-RETR-032
Severity:      LOW
Reachability:  REACHABLE today. Every zero-evidence response.
Rubric:        ROUTE-01 (acceptance: "100% of zero-evidence responses carry: queries executed,
               constraints dropped with reasons, per-rung hit counts, what was not tried, and
               **affordances**"); AD-03 (an affordance is a concrete call that would reach the
               untried rung).
Location:      server/src/mailweave/retrieval/assemble.py, assemble / _empty_diagnosis —
                 no affordance is produced for the report class;
               server/src/mailweave/envelope/response.py,
                 Envelope._no_bare_empty_response, whose docstring describes the report as
                 carrying "the parse, the tokens dropped and why, an `empty_diagnosis` and
                 the affordances"
Repro:         /tmp/rretr17/p12_report.py, p13_report2.py
                 for every one of 'thread:1837abf', 'tel:+15550100', '(zephyr OR borogrove)',
                 '{zephyr borogrove}', 'the and of', '?', '""', 'subject:', 'in:anywhere',
                 'in:spam', 'borogrove', 'from:nobody@parts.example borogrove':
                   envelope.affordances == []   empty_diagnosis.affordance is None
                   scan_scope affordances: none   withheld: none
Expected:      Where a concrete call exists that would reach a rung, the zero-evidence report
               offers it. For `thread:1837abf` that is searching `"1837abf"` as a quoted term;
               for `(zephyr OR borogrove)` it is searching `zephyr borogrove`; for
               `in:anywhere` it is adding something to look for.
Actual:        The report class — this round's new class, and the one whose whole purpose is to
               tell a calling agent what to do instead — offers nothing. Affordances are minted
               only by `_empty_diagnosis` (a restoring drop, or a budget-bound untried drop),
               neither of which applies when no rung ran.
Required fix:  Mint an affordance in the report path from the declaration that produced it:
               `unproven_operator` -> re-run with the token quoted; `unparsed_syntax` -> re-run
               with the boolean tokens removed (which is what `render` would have executed);
               `selects_nothing` beside nothing else, and `carries_nothing_but_mailbox_scope`
               -> a search call with a `terms` slot. Keep R-RETR-023's rule: offer nothing when
               nothing would help, rather than minting a call that changes nothing.
```
```
ID:            R-RETR-033
Severity:      LOW
Reachability:  REACHABLE in the test suite only — this is the double, not the product. Under
               §5a it is not a product finding; I raise it because it bounds what any
               end-to-end claim in this round can cover, mine included.
Rubric:        AL §7.2 (a fixture that cannot evaluate what the ladder sends); LEX-02 evidence
               scope; EV-05 clause 2 evidence scope.
Location:      tests/fixtures/mailbox.py, _date_value / epoch_ms — `_date_value` matches
                 `\A(\d{4})/(\d{1,2})/(\d{1,2})\Z` and then calls `datetime(...)`, which raises
                 for an out-of-range month, day or year
Repro:         /tmp/rretr17/s2_plausible.py, and directly:
                 mailweave_search('after:2026/13/45 zephyr')
                   -> ValueError: month must be in 1..12, raised at
                      tests/fixtures/mailbox.py:92, out of LadderRunner.run
                 same for 'before:2026/02/31 …', 'after:0000/01/01 …'
                 MailWeave itself is correct here: `parsed.window is None`, the fragment is
                 carried unchanged, and the ladder plans
                 L1 'after:2026/13/45 zephyr' / L1b / L2 / L3 'in:anywhere zephyr'
Expected:      The double refuses an operator it does not implement, deliberately; it should
               likewise return "no match" (or refuse loudly and be handled) for a *value* it
               cannot evaluate, rather than raising an uncaught ValueError through the client.
Actual:        A plain user query with an out-of-range date crashes every end-to-end test
               harness that uses this fixture. No test in the suite covers such a query, so the
               crash is invisible today; the consequence is that no end-to-end statement about
               out-of-range dates — a documented A.6a case, since MailWeave deliberately lets
               Gmail judge them — is establishable against this double by anyone.
Required fix:  `_date_value` returns `None` for a syntactically-matching but calendar-invalid
               date (the `None` path already means "Gmail judges it, we do not"), and a test
               drives `after:2026/13/45` end to end so the path is executed. Separately, record
               `category:` and the other eight `OperatorName` members the double does not
               evaluate as the standing ceiling they are (already named in IMPLEMENTER §9).
```
```
ID:            R-RETR-034
Severity:      LOW
Reachability:  REACHABLE today. A fullwidth-typed query from an IME reaches `analyse`
               unchanged. Pre-existing — not introduced by this round's diff.
Rubric:        LEX-02 (a signal reinterpreted rather than enforced or dropped); the residue
               `widens_beyond_the_default_mailbox` names in its own docstring.
Location:      server/src/mailweave/query/operators.py, tokenise (no NFKC normalisation)
                 against server/src/mailweave/constants.py, _operator_token and
                 matchable_content_of (both NFKC-normalise). Three modules, two answers.
Repro:         /tmp/rretr17/s4_recall.py, and directly:
                 mailweave_search('ＩＮ：ＡＮＹＷＨＥＲＥ zephyr')
                   parsed constraints [('terms','terms',('anywhere','zephyr'))]
                   wire ('anywhere zephyr', False), ('anywhere', False), ('zephyr', False),
                        ('in:anywhere anywhere zephyr', True)
                   the spam message the caller asked for is NOT found
                   enforced ('terms', 'stopwords_removed:in:anywhere')
                 carries_nothing_but_mailbox_scope('ＩＮ：ＡＮＹＷＨＥＲＥ') is True, so the
                 guard and the parser disagree about the same token
Expected:      Either the fullwidth spelling is the scope operator everywhere (and the query
               is scoped as written), or it is a term everywhere (and `constants` stops
               claiming to normalise it). One token, one reading.
Actual:        The parser reads it as a term, the term pipeline strips `in:` as a stopword, and
               MailWeave searches for the word `anywhere` in the default mailbox. The caller's
               region request is silently reinterpreted into a term they did not write, which
               additionally *narrows* the query. Declared only indirectly, through
               `asked_for.parsed.terms` and a `stopwords_removed:in:anywhere` entry inside
               `enforced`.
Required fix:  This is the query-normalisation policy question the implementer already
               escalated (A.6 / WS-10) — whether a user's query is normalised the way mail text
               is. Whichever way it is decided, `tokenise` and `constants._operator_token` must
               apply the same normalisation, and the decision must be written where both read
               it. Until then, the residue belongs in `widens_beyond_the_default_mailbox`'s
               named-residue list, which currently claims fullwidth is covered.
```

---

## Recommendations, per criterion

**I mark nothing.** Every recommendation is scoped and I name what my evidence does not cover. I
revisit LEX-01..04, EV-02, EV-04..06 and ROUTE-01..04 on this round's code, and I say where I differ
from the round-16 instance.

* **LEX-01 · Message-level search is the first rung — RECOMMEND PASS, scoped** (round 16: PASS
  scoped; I confirm on this round's code, and one of its two scope notes is now gone).
  Evidence: `call_log[0]` is `messages.list` with a non-empty `q` in every run that reaches Gmail —
  600 randomised trials, 120 overflow trials, my 58-query plausible audit, my 22 recovery cases, all
  three A.8a branches. `hit_threads` derives `H`'s hit half only from `MESSAGES_LIST` origins, so no
  thread listing can feed it. **Round 16's first scope note is closed**: the vacuous class no longer
  makes the first call `q='""'`; it makes no call. **The second scope note survives in a smaller
  form**: for the report class (7 of my 58 plausible queries) there is no first Gmail call at all, so
  "the first call is `messages.list`" is vacuously true there — which is now the intended behaviour
  rather than a refusal. Not covered: the live account.

* **LEX-02 · Operator-parse fidelity and coverage reporting — RECOMMEND NOT PASS** (round 16: NOT
  PASS; unchanged, on new grounds — two of its three blocking counts are closed and three new ones
  are open).
  Closed and independently re-established: **R-RETR-018** (nine colon-carrying phrase shapes reach
  Gmail with `term_coverage 1.0`), **R-RETR-017** (no vacuous token becomes a constraint, for every
  spelling I could enumerate in the operator family), **R-RETR-020's L3-only and L0-stop cases**
  (`from:… zephyr` answered only by `in:anywhere zephyr` now reports `enforced ('terms',)`,
  `term_coverage 0.5`, and names `from` dropped with L3), **R-RETR-025**, and **R-RETR-024(c)**
  (the A.7 cap now moves the claim: 4/5/6 units → `enforced ()`, `term_coverage 0.0`).
  Blocking: **R-RETR-027** (a signal executed inverted and reported enforced — the acceptance's
  "signals silently dropped: 0" fails in its worst form), **R-RETR-028** (a constraint reported
  enforced from one fragment of it, at both L0 branches, with the row's `constraint_coverage`
  repeating the claim), **R-RETR-030** (`enforced`/`term_coverage` true of no single route that
  admitted the disclosure), **R-RETR-029** and **R-RETR-034** as smaller instances.
  The scope question round 16 declined to score I decline too, for the same reason: an L1b piece
  probe's rows carry `constraint_coverage: ()` (4 of 21 matched rows in my battery). The field is
  present and the emptiness is the conservative direction; whether an empty tuple satisfies "every
  disclosed message carries `constraint_coverage`" is a contract reading, not an execution result.

* **LEX-03 · Multi-constraint decomposition — RECOMMEND NOT PASS, and the gap is now small**
  (round 16: NOT PASS on R-RETR-019).
  **R-RETR-019 is closed and I reproduce it independently**: the founding shape recovers in the
  inbox, in spam, in trash and under `in:anywhere`, on my own fixtures, with the scope on every unit
  and `include_spam_trash` agreeing. Plus 3/4/5/6 bare words, operator+term splits at two and four
  operators, repeated operators de-duplicated to one unit, a written-out window as one unit. That is
  the project's founding bug, fixed at the constraint model, and it is again the strongest thing in
  the round.
  Blocking: **R-RETR-026's L1b half** — a decomposition probe still drops a *negated* region
  fragment, so `in:anywhere -in:spam a b` searches the spam the caller excluded. Independently, the
  criterion's recall bar is `[UNSET — register at G0]` against a Baseline D that does not exist, so
  no rate can be reported by anyone this round.

* **LEX-04 · Exact-signal stop — RECOMMEND NOT PASS. I disagree with round 16's scoped PASS on this
  round's code, and say so plainly.**
  What holds, re-established on a 40-message thread of my own: branch E-a resolves with
  **rungs executed = 1**, `stop_rule` D.3-1, the message at `body_clean`, 1 `messages.list`, zero
  embedding/model/reranker calls (none exist; the `generative-client` guard is clean). Round 16's
  own scope note is closed — E-b now fires for a phrase containing a colon.
  What blocks, and it is inside the criterion rather than beside it: **R-RETR-028**. "Exact-signal
  queries resolve on the cheapest rung" is satisfied; what the round-16 instance recorded as
  "a LEX-02 defect reached through LEX-04's stop" I now find is *produced by the stop's own rung*.
  `PO-2026-0041 zephyr` and `"…" "…"` halt at L0 under D.3 rule 1b having executed one fragment,
  and the response says it enforced the whole constraint at `sufficiency: sufficient`. A stop that
  is cheap and wrong is not the criterion passing. Not covered, unchanged: the cost bar is a
  network-level median over a family distribution; a `MockTransport` boundary is one case per
  branch. **WS-16 / R-PERF.**

* **EV-02 · Position-independent evidence recall — CANNOT ESTABLISH.** No EP §4.4 corpus, no
  ~100-message thread family, no holdout seed, no two-seed CI, no DISC-04/PERF-01 on the same run.
  **WS-16.**

* **EV-04 · Zero false "not found" — RECOMMEND NOT PASS, with the letter noted again.** Over roughly
  1,100 executed runs this round, `not_found` was never emitted and cannot be — `NOT_FOUND` appears
  nowhere in `retrieval/`, and `Envelope._outcome_matches_the_payload` refuses it against a withheld
  record or an unfetched page. So the rate is trivially 0 and stays 0 while `outcome` has two
  reachable values. That is not evidence for the criterion. Its **paired hallucinated-found rate**,
  which the criterion says may never be reported alone, is what R-RETR-026, R-RETR-027, R-RETR-028
  and R-RETR-030 are shaped like: rows from a region the caller excluded, a phrase matched when it
  was to be excluded, a constraint claimed from a fragment, and a claim true of no route that
  produced the disclosure. **WS-16** for the measurement; the four findings block regardless.

* **EV-05 · Issue #296 signature — adjacent, one note in each direction.** Clause 1 re-established on
  my own 40-message thread: `rfc822msgid:<deep17@…>` returns that message at `body_clean` on one
  rung, one Gmail list call, `role: matched`. Clause 2 is **better than round 16**: the R-RETR-024(b)
  reproduction (a Jan-2025 message under `newer_than:7d`) now discloses that row with
  `constraint_coverage` *omitting* `newer_than` and with `asked_for.dropped` naming the constraint
  and the rung; the criterion's "or explicitly declares the ones that are not and why" is met by an
  absence rather than a positive statement, which a reader of a PASS must know. Both halves still
  need the live account. **R-GMAIL.**

* **EV-06 · Recall against the full-dump ceiling — CANNOT ESTABLISH.** No Baseline B, no corpus
  instance, no paired scoring, no interleaved session. **WS-16.**

* **ROUTE-01 · No bare empty response — RECOMMEND DO NOT RESTORE THIS ROUND. One named, small
  ground, and I say exactly what my evidence covers.**
  **What I established, and it is the whole of the regression the revert was recorded for.** Over
  ~1,100 executed runs — 600 randomised preservation trials, 120 overflow trials, 338 fuzz inputs,
  58 plausible queries, 22 recovery cases — there were **0 bare empty responses, 0 nonexistence
  claims (`not_found` never emitted, OD-2 held), and 0 refusals of any non-empty query**. The only
  inputs that raise are whitespace-only, and the reason given for that — that a report there would
  read `term_coverage 1.0` and `empty_diagnosis: complete` — I verified by execution rather than
  accepting. Every zero-evidence response carried the ladder account (rungs executed, or all five in
  `not_tried`), the scan scope, the per-rung hit counts, the constraints dropped with non-empty
  reasons, and an `empty_diagnosis`. Round 16's "17 of 50 produce no envelope" is gone, measured on a
  set the implementer did not build.
  **Why I still do not restore it.** ROUTE-01's acceptance enumerates five things and the fifth,
  affordances, is absent from every zero-evidence response I produced (**R-RETR-032**) — including
  the class this round created, where concrete affordances plainly exist. This project has twice
  reverted a criterion because a scoped recommendation was recorded as an unqualified PASS
  (INJ-04 round 4, PART-07 round 4) and its own rule is that "a criterion is passing or it is not;
  there is no half". Restoring it now with a fifth-of-the-acceptance caveat would set that up a third
  time. R-RETR-032 is LOW and small; close it and ROUTE-01 is one reviewer-run from PASS at full
  scope, and I would restore it then.
  Not covered by anything I ran: the live account, and the MCP tool surface (I drove
  `LadderRunner` + `assemble` directly, as `mailweave_search` does).

* **ROUTE-02 · Mis-parse recovery — CANNOT MARK PASS; measured on a set I built, and the shortfall
  named.** On my own 22 constructed recovery cases (`/tmp/rretr17/s4_recall.py`, none shared with
  either prior instance): **21/22 recovered, 0 false-not-found, 0 refusals.** The one failure is
  R-RETR-034 (the fullwidth scope operator), a mis-parse the ladder does not recover from because the
  mis-parse *adds* a term. Round 16's two refusal classes are gone. The bar is
  `[UNSET — register at G0]`, so no one can mark this criterion this round.

* **ROUTE-03 · Relaxation is systematic and enumerable — RECOMMEND PASS, scoped** (round 16: PASS
  scoped; I confirm on this round's code, which changed `Probe.dropped` and `_routes` around it).
  Re-established by independent replay: one constraint dropped per probe; `_ordered_for_relaxation`
  over `parsed.constraints` unchanged; each step logs the constraint, the `q` and the hit count;
  `max_relax_probes = min(k,6)` binds at k=9 with the three unreached drops named in `untried_drops`;
  the sequence is a function of the query alone. **The round's own change did not disturb it**:
  `Probe.relaxes` is still true at L2 and nowhere else — I checked that `Broadening.given_up`
  populates `Probe.dropped` at L3 *without* setting `relaxes`, so a broadening is not counted as a
  relaxation in `relaxed_away` or in `RelaxationStep`. Scope: the guarantee still has no subject for a
  one-constraint query, which is a ROUTE-04 gap rather than a ROUTE-03 one.

* **ROUTE-04 · Empty-result diagnosis — RECOMMEND NOT PASS, and I now disagree with round 16's
  reason while reaching its verdict.** **R-RETR-023 is closed and I reproduce it**: at k=1 the
  diagnosis reports `incomplete` with `untried_drops ('terms',)` and **`affordance: None`**, while a
  crowded 9-constraint query still gets `{"relax": {"max_probes": 9}}`. `plannable_drops` and `plan`
  share one expression, so the offer cannot promise a probe the planner refuses. Correctness over
  probed drops re-measured on my own constructed cases where I chose the restoring constraint:
  `complete` with the right `restores` where one drop restores, `complete`/`restores: None` where
  none does, `incomplete` with a complete `untried_drops` at the budget, `None` on an answered
  response, `outcome: inconclusive` in every incomplete case. What blocks now is different from round
  16's ground: for the report class the diagnosis reports **`complete`** on a run in which **no drop
  was probed and no rung ran** — vacuously true, and the third ADV-105 state ("structurally
  unprobeable at any budget") still has no vocabulary value, which the implementer records as
  **WS-10**. Combined with R-RETR-032 (the report's diagnosis is case-specific but offers nothing),
  the criterion's own guard — "ruled out by ROUTE-04's requirement that the report's diagnosis be
  case-specific and correct" — is not fully carried. The incomplete-diagnosis-rate ceiling is
  `[UNSET — G0]` independently.

---

## Overall verdict

**Round 17 does not close.** Three HIGH, three MEDIUM and three LOW findings, all reachable from
ordinary query strings through code that exists and executes today. I raise no BLOCKER: round 15's
and round 16's blocker shape — a query whose content was never executed answered with a whole-mailbox
read reported as `answered` at `term_coverage 1.0` — is closed for every spelling I could enumerate
in the operator family, and the empty-selection family now costs zero Gmail calls. R-RETR-029 is the
one path back to it and its severity turns on a Gmail behaviour nobody here can measure.

**This round is the best of the three at the thing it was asked to do.** The report/raise line is
right, it survived 338 adversarial inputs, and the reason given for the one class that still raises is
true on execution rather than plausible in prose. R-RETR-017, 018, 019, 021, 022, 023, 025 and
024(c) are genuinely closed and I reproduced each independently. The invariant is real, its test is
not vacuous, and I established that by planting four violations that it caught — including one that
empties the very derivation the test reads.

**What it did not do is finish the sentence it wrote.** The invariant classifies a negated mailbox
scope as "a negation", and that one classification is the thirteenth instance of this project's
recurring defect at the same join: 201 planned probes in a 5,979-query sweep, and 47 of 600
randomised end-to-end trials, disclose as `matched` exactly the messages the caller excluded. The
rule Part 4 wrote for L1b and L3 — a constraint is enforced only by a route that carried it whole —
was not carried to L0, where the ladder's strongest stop then freezes the over-claim. And Part 2's
fix, correct in itself, newly routes a negated quoted phrase into a path that discards its polarity
and searches for the phrase the caller asked to exclude.

All three are small edits in this round's own code, and two of them are unasserted by any test today
(plants N1 and N3 leave 2,248 green), so they can be made without fighting the suite.

---

## Established by execution

* All six gates reproduce, twice, unchanged: ruff, ruff format (153), mypy --strict (127),
  7 guards, **2,248 tests** (independently re-counted by collection), rubric 6/0/0/107 with
  11 transitions.
* **R-RETR-017 closed** for the operator family: `""`, `" "`, `""""`, `"\t"`, `"\xa0"`, `subject:`,
  `label:`, `is:`, `in:`, `has:`, `subject:""`, `label:""`, `(subject:)`, `{}`, `()`, U+200B,
  U+200F, U+061C, and fullwidth `Ｓｕｂｊｅｃｔ：` all produce a structured report with **zero Gmail
  calls**. `matchable_content_of`'s claim to hold for an operator nobody has enumerated is true and
  structural — it never consults `OperatorName`.
* **R-RETR-018 closed**: nine colon-carrying phrase shapes parse as phrases, reach Gmail verbatim and
  report `term_coverage 1.0`; `thread:1837abf rollout` is still an unproven operator, kept off the
  wire and declared.
* **R-RETR-019 closed**: the founding shape recovers in the inbox, in spam, in trash and under
  `in:anywhere`, on my own fixtures, with the scope carried onto every decomposition unit.
* **R-RETR-020's L3-only and L0-stop cases closed**: a run whose evidence came from
  `in:anywhere zephyr` reports `enforced ('terms',)`, `term_coverage 0.5` and names `from` dropped
  with L3 beside it.
* **R-RETR-021 closed at the code**: every narrowing location is replaced rather than conjoined, and
  `in:anywhere is:unread` plans no broadening at all.
* **R-RETR-023 closed**: `affordance: None` at k=1, a budget affordance at k=9.
* **R-RETR-025 closed**: a repeated identical fragment is one unit, labels unique.
* **R-RETR-024(c) closed**: at 4, 5 and 6 decomposition units the thread is still recovered and the
  response reports `enforced ()` / `term_coverage 0.0` rather than claiming the constraint the cap
  prevented it from probing.
* The invariant test is **not vacuous**: emptying `mailbox_scope_of` still fails it, through an
  independent `include_spam_trash` oracle. Four of six planted violations are caught by it alone.
* **Evidence preservation holds** across every new path: 600 randomised trials plus 120 designed to
  force `max_hit_threads` overflow (45 of which produced withheld records) — 0 violations of
  `H ⊆ disclosed ∪ withheld`, 0 disclosed/withheld overlaps, 0 phantom ids, 0 probes into spam or
  trash that were not either asked for or L3's published step.
* **The report/raise line holds**: 338 adversarial inputs, 335 envelopes, 3 raises, all
  whitespace-only, 0 uncaught exceptions from MailWeave's own code.
* **The 16-plant reintroduction is sound**: the harness asserts its imports resolve inside
  `/tmp/r17impl/tree` and not into the real tree; all 16 plants re-run in my own scratch tree are
  CAUGHT by the test each names.
* **The P2 "MISSED on first run" disclosure is accurate**: with its own test deselected, the whole
  suite is green with the clause removed.
* **The five new defects above**, each with a reproduction: the negated-region leak (201 probes /
  47 trials), the inverted negated phrase, the L0 fragment-as-constraint over-claim at both branches,
  the blank-character wire shape, and the union-over-routes claim.

## False on execution

* **"A probe composed from a subset of a query's fragments searches the region the query named"** —
  false when the region was named by exclusion. `-in:spam -in:trash borogrove` discloses a spam
  message and a trash message as `matched`.
* **"Omitting a negation widens within the region"** — false for `-in:spam` / `-in:trash`, which are
  the only negations whose omission crosses the spam/trash boundary. The asymmetry table's first row
  is wrong for its own most important member.
* **"The invariant … is enforced once, by one membership test over `LADDER` with two enumerated
  exemptions"** — R-RETR-021's own defect, planted back, leaves that test green; a different test
  holds it. The L3 exemption checks that the probe widens, not that it "replaces wholesale".
* **"`matchable_content_of` … holds for spellings nobody enumerated"** — it removes one Unicode
  category. U+3164, U+2800 and lone combining marks are "content", and U+3164 reaches the wire as
  `in:anywhere ᅠ` with `includeSpamTrash=true`.
* **"`enforced` is derived from what every executed rung actually enforced"** — the union over routes
  restores the over-claim whenever a carrying and a non-carrying route both contribute to the
  disclosure (`in:inbox zephyr` → `enforced ('in','terms')`, `term_coverage 1.0`, over a row that is
  not in the inbox), and L0's two branches never had the rule applied to them at all.
* **"A colon inside quotes is content"** — true, and correct; but the same change makes
  `-"Re: quadrant"` a *positively searched* phrase where round 16 dropped and declared it. The
  round's own test for that case asserts only that it is a phrase.
* **"Every response … `asked_for.dropped` … plus the affordances"** (`_no_bare_empty_response`) —
  no zero-evidence response I produced carried any affordance.

## Not establishable here at all

* **Whether Gmail returns the whole mailbox for `q` = a single blank-rendering character**
  (U+3164, U+2800, a lone combining mark). This decides whether R-RETR-029 is a MEDIUM or the
  BLOCKER returning. **R-GMAIL / PF-20.**
* **Whether Gmail reads `"9:30 standup"` as one phrase or two tokens**, and whether it treats
  `subject:` with an empty value as a no-op or an error. **R-GMAIL / PF-9.**
* **Gmail's system label vocabulary**, without which `label:inbox` cannot be told from a user's own
  label — the `label:` residue in `names_a_mailbox_location`, which I confirm is open and correctly
  declared. **R-GMAIL / A.6.**
* **Every rate the rubric asks for**: LEX-03's and ROUTE-02's recall bars, EV-02's position sweep,
  EV-04's paired hallucinated-found rate, EV-06's Baseline B comparison, ROUTE-04's
  incomplete-diagnosis ceiling. All are `[UNSET — register at G0]` or need a seeded corpus, Baseline
  B/D, holdout seeds and a counting proxy. **Every number in this review is on sets I constructed and
  is offered as nothing else. WS-16.**
* **LEX-04's cost bar**, which must come from network-level counts rather than a `MockTransport`
  boundary. **WS-16 / R-PERF.**
* **A ceiling on all of the above, mine and the implementer's**: the double evaluates 13 of 21
  `OperatorName` members and raises `UnimplementedOperator` on the rest (I hit it on `category:`),
  and it raises an uncaught `ValueError` on a calendar-invalid date the parser accepts and sends
  (R-RETR-033). Every end-to-end statement in this round is bounded by that.
