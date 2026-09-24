# ROUND 08 — Implementer handoff

**Implementer, 2026-08-31.** Scope: `docs/reviews/ROUND_08/WORK_ORDER.md`, four parts.
Amendments A1..A6 binding; **A6's final amended form built this round**. A1 not built and
not mine. OD-1..OD-4 binding.

## Verification state

| | Baseline (round 7 tree) | This tree |
|---|---|---|
| `ruff check` / `ruff format --check` | clean, 88 files | clean, 91 files |
| `mypy --strict` | clean, 62 source files | clean, 65 source files |
| `pytest -m "not network"` | **775 passed** | **823 passed** |
| `python -m tools.guards` | 7 guards clean | 7 guards clean |
| `rubric_status.py --check` | 8 PASS / 105 NOT TESTED / 10 transitions | **unchanged** |
| `make check` | exit 0 | exit 0 |

No rubric criterion marked PASS. No rows added to `RUBRIC_TRANSITIONS.md` or
`FINDINGS_LEDGER.md` (both byte-unchanged). Every count below was obtained by running the
suite and reading its last line.

**Dependency change:** `email-reply-parser` is removed from `server/pyproject.toml`,
`uv.lock` and the mypy overrides. Nothing imports it; `uv run python -c "import
email_reply_parser"` now fails. Part 1 says why.

---

# Part 1 — R-ARCH-022, the BLOCKER

## What I did: stopped delegating the decision, and said so

The work order offered the option and it is the right one. `email_reply_parser` decided
deletions on three of its own patterns — `QUOTE_HDR_REGEX = 'On.*wrote:$'`, a **one-line**
`^\*?(From|Sent|To|Subject):\*? .+`, and `SIG_REGEX = '(--|__|-\w)'` as a *prefix* test —
and, on a match, retroactively marked every fragment below it `hidden`. `strip_quotes_and_
signature` then deleted those fragments in a branch that never reached A5's rule. There is
no wrapper fix for this: by the time this module sees a fragment, the sentence is already
inside it. A dependency that silently deletes user text cannot be audited afterwards.

`content/quotes.py` now owns the segmentation end to end. `email_reply_parser` is gone from
the deletion path and from the dependency list. `stripper_version()` reports
`mailweave.content.quotes@a5-round8`, because reporting a distribution that no longer
decides anything would attribute this module's rules to somebody else's code.

`ARCHITECTURE_DECISION.md` §D.4a-6 carries a dated supersession note. **The amendment entry
in `ARCHITECTURE_AMENDMENTS.md` is the orchestrator's to write** — I did not author one;
A1..A6 are the amendment set I was given and adding A7 on my own word is the failure this
project keeps catching. `IMPLEMENTATION_PLAN.md`'s WS-07 row still names the library and
also needs the orchestrator's pen.

## The rule, as code rather than as a docstring

Every removed character belongs to a region opened by one **named** strong structural
signal, and `strip_quotes_and_signature` raises if a line is marked for removal carrying
none. The signals:

| Signal | What it is | Extent |
|---|---|---|
| `quote_marker` | a run of `>`-prefixed lines | the run |
| `forward_separator` | `-----Original Message-----`, `Begin forwarded message:`, `---------- Forwarded message ---------` | **latches** to end of message |
| `header_block` | **two or more distinct** `From:`/`Sent:`/`To:`/`Cc:`/`Subject:`/`Date:` fields on consecutive lines | **latches** |
| `client_attribution` | a line matching `_client_attribution_template` | the line |
| `client_attribution_unmarked_block` | the same line with **no `>` run below it** | **latches** |
| `signature_delimiter` | a line whose whole content is `--` or `__` (RFC 3676) | to the end of its kept run |
| `signature_sign_off` | a recognised sign-off or mobile footer, body above, few short lines below | as above |

Three changes carry the fix specifically:

* the header rule counts **distinct** fields, so `To: whoever reviews this next, please
  check the totals.` is a sentence, not a header;
* the signature delimiter is a **whole-line** match, so `-1 day change to the schedule`
  opens nothing;
* a `>` run and an attribution line **do not latch**, because inline replies are ordinary
  mail and the library's latch deleted every answer in one.

MIME boundaries are named in A5 and deliberately **not** implemented here: `content/mime.py`
consumes them before this module runs, and a boundary detector over decoded text is the
same dash-prefix shape whose false positives this round exists to close. Stated in the
module docstring rather than left as an implied gap.

## Failing-test-first evidence, counted by running

Each of the library's three rules reintroduced faithfully into the new segmenter, full
suite run, file restored and diffed byte-identical before the next:

| Reintroduction | Failing tests |
|---|---|
| `_HEADER_BLOCK_MIN_FIELDS = 1` (the library's one-line `HEADER_REGEX`) | **6** |
| `_SIGNATURE_DELIMITER_LINE_RE` back to the prefix form `(--|__|-\w)` | **4** |
| `On.*wrote:$` accepted as an attribution signal (the library's `QUOTE_HDR_REGEX`) | **17** |

And the whole-tree measurement, which is the number that matters: the **round 7 stripper**,
run against this round's three corpora in both positions, destroys **25 of 200**
sentence/position pairs. This tree destroys **0 of 200**.

## The gated metric: false positives, per corpus per position

`Two points before Friday.\n\n{line}\n\n> The freeze starts Friday.\n` for `above_quote`;
`Thanks for the update on this.\n\n{line}\n\nWe should have a decision by end of week
either way.\n` for `standalone`. **The surrounding sentences are asserted too** — R-ARCH-022
destroyed the sentence *and* the unrelated paragraph after it, so a test that checked only
the sentence would have under-reported the failure it was measuring.

| Corpus | `above_quote` | `standalone` | round 7 tree, same corpora |
|---|---|---|---|
| `implementer_round_7` (36) | **0/36 = 0.0%** | **0/36 = 0.0%** | 0/36 · **4/36 = 11.1%** |
| `r_arch_round_7` (35) | **0/35 = 0.0%** | **0/35 = 0.0%** | 0/35 · 0/35 |
| `implementer_round_8` (29) | **0/29 = 0.0%** | **0/29 = 0.0%** | **7/29 = 24.1%** · **14/29 = 48.3%** |
| **All three** | **0/100** | **0/100** | 25/200 = 12.5% |

**A discrepancy in R-ARCH's own report, recorded rather than smoothed over.** §1a reports
"0/36" and "72/72 kept"; its published table lists **35** distinct sentences (8 + 5 + 5 + 5
+ 6 + 6). All 35 are transcribed into `R_ARCH_ROUND_7_PROSE`. The 36th is not recoverable
from the report, and inventing one to make the arithmetic close would be the tidying this
project refuses. The rate over 35 is zero.

The round-8 corpus is written against the segmenter that replaced the library, not against
the one that failed: R-ARCH-022's four destroyer sentences and six more of that shape, the
`To:`/`From:`/`Subject:`/`Sent:` paragraph openings, the dash and underscore line
openings, six locales of prose carrying a real weekday **and** a real date **and** an
address **and** a terminal colon **and** a first-person subject (the attack on Part 2's
calendar mask), and the ordinal-date sentence Part 2 declares a gap for.

## Every deletion carries a `Reduction`; ambiguity carries a zero-sized one

Unchanged in shape and now checked as a property over the whole corpus:
`bool(quoted_chars + signature_chars) == bool(removal_signals)`, so a removal with no
signal or a signal with no removal fails. The ambiguity clause fires when an
attribution-*shaped* line matches no client template **and** sits directly above something
that was removed: the line stays, `ambiguous_lines` counts it, and `pipeline.py` emits a
`Reduction(kind=QUOTED, removed_chars=0, count=n)` whose reason names the rule and carries
no mail text (R-09). The same line with nothing removed near it is prose, not ambiguity,
and is not declared — being unsure is a claim, and it should not be made when it is false.

New this round: each `quoted`/`signature` reduction's `detail` **names the signal that
opened it**, and says so explicitly when the removal latched. See "where this is weakest".

---

# Part 2 — the false-negative correction

## The collision

`_FIRST_PERSON_RE` unions pronouns across ten locales and every client attribution carries
a weekday abbreviation: en `Mon` / fr `mon`, de `Mi.` / es `mi`, nl and fi `ma` / fr `ma`,
sv `ons` / nl `ons`. The pronoun check disqualified the header, so a well-formed,
addressed, correctly-shaped attribution survived — on Mondays in en/nl/fi and Wednesdays in
de/sv. Every worked example in `reply_chains.py` was a **Tuesday**, which collides with
nothing.

## The fix

`_calendar_masked` blanks the calendar expression before the first-person scan, and only
that: it finds the `_WHEN_PATTERN` span and extends it left across a single weekday token,
which is where every client puts one. It runs **only when a full calendar date is present**,
and it can only ever remove a disqualification — so the lines whose answer it changes are
exactly those already carrying a lead-in, a date, an address and a final verb. `"On Mon, 25
August 2026 I wrote to priya@example.com and she wrote:"` keeps its `I`: the mask covers
`Mon, 25 August 2026` and stops.

Reintroduction: reverting `_client_attribution_template` to scan the unmasked line breaks
exactly **4** tests (`...one_weekday[Monday]`, `[Wednesday]`, the residue test, the rate
test).

## The re-measurement

**7 weekdays × 23 client formats = 161 cases.** 2026-08-24..30 is exactly Monday to Sunday,
so one calendar week indexes the seven days with real dates. Formats: Gmail in ten locales
plus the address-less English form, Outlook desktop with and without an address, an Outlook
Web header block, Apple Mail macOS and iOS, Gmail for Android, a Yahoo forwarded block,
ProtonMail, Thunderbird, a mailing list's parenthesised address, and bare `>` / `>>` chains.
Formats that print no weekday still move through the week by date.

| Tree | Surviving headers | Rate | Weekday-dependent formats |
|---|---|---|---|
| Round 7 (same corpus) | 36 / 161 | **22.4%** | **8** — gmail_en, gmail_nl, gmail_fi, apple_mail_ios, android_gmail, mailing_list_paren on Monday; gmail_de, gmail_sv on Wednesday |
| This tree | 28 / 161 | **17.4%** | **0** |

R-ARCH measured 36.8% on its own 19 headers; 22.4% here is the same defect measured against
a differently-weighted corpus, and the eight weekday-dependent formats are exactly its
table. The residue is now **uniform across all seven weekdays** and is two named shapes:

| Format(s) | Cases | Why it survives |
|---|---|---|
| `gmail_en_no_address`, `outlook_no_address`, `thunderbird` | 21 | **no address on the line** — amendment A5's declared gap. Dropping the address requirement is what puts "On 25 August 2026 the vendor wrote:" back in range |
| `protonmail` | 7 | **an ordinal date** (`24th August 2026`), which `_WHEN_PATTERN` does not read |

The residue is pinned in both directions by
`test_the_false_negative_residue_is_exactly_what_is_declared`: the surviving set must be
exactly the declared one, and each surviving format must survive on **all seven** days — a
format that survives on four of seven is the collision coming back.

False negatives stay **reported, not gated**, per A5.

---

# Part 3 — amendment A6, final amended form

## What landed

`FetchedIds` widens to carry the named scalars the class-O audit identified, and **only**
those: `stated_total` and per-id `positions` (a `threads.get` fact — a listing page is a
page of a result set, not a thread, and is refused if it states either), per-id
`internal_dates`, and response-level `history_id` and `fetched_at`. Every per-id map must
name **exactly** the ids the observation returned, which is `thread_ids`' rule since
R-DISC-009. `positions` must be distinct and satisfy A3's `0 <= p < stated_total`;
`stated_total` may not be below the number of ids the response returned; `fetched_at` must
parse as an instant with an offset.

Those facts flow into `HitOrigin` (`position`, `internal_date`) and a new frozen
`ObservedThread` (`stated_total`, `history_id`, `fetched_at`), accumulated per thread by
the ledger. A later observation may **fill** a fact an earlier one did not carry — the
ordinary ladder is a `messages.list` page then a `threads.get` — and two observations that
**disagree** are refused rather than resolved, which is `HitOrigin.thread_id`'s rule applied
to the scalars A6 seals. `DispositionCertificate` carries `observed_positions`,
`observed_internal_dates` and `observed_thread_facts`, so the envelope checks against the
same enumeration the set difference was computed from.

## Parameters removed, and parameters that stayed — with the reason

**Removed** (the two class-O fields with no reader inside the model, both filed `open` in
round 7):

| Field | Route |
|---|---|
| `MessageRow.internal_date` | gone from `model_fields`; `Envelope` writes it onto each row's wire form from `observed_internal_dates`, in D.2's position, right after `position` |
| `Source.history_id` | gone from `model_fields`; `Envelope` writes it from `observed_thread_facts`, right after `verified_at` |

This is `MessageRow.thread_id`'s round 7 route one level further up — the fact lives on the
certificate, and `Envelope` is the first object holding both the certificate and the
payload. An id or thread the ledger never observed gets **no field written**, not a `null`:
"this response does not know" and "this response says none" are different statements.

**Stayed, and are now checked totally instead of bounded** — I am stating this plainly
rather than implying a removal I did not make:

| Field | Round 7 | Now | Why not removed |
|---|---|---|---|
| `Source.stated_total` | bounded below | **exact** against the observation where it recorded one | `Source` reads it in four validators (`complete_as_reported`, map accounting, A3's range, stub arithmetic) |
| `NotIncludedSource.stated_total` | bounded below | **exact** | same fact, same reason |
| `MessageRow.position` | bounded (A3) | **exact**; and a collapsed run must span its members' observed positions | `Source`'s occupancy and A3 range validators read it |
| `Source.fetched_at` | parses as an instant | **exact** against the call | `Source` orders it against `verified_at` |

Removing these needs the observation threaded through `Source` and `MessageRow` — a second
structure carrying the ledger's facts alongside the ledger, which is the "parallel structure
that silently drops a field" cost round 7 named. The lower bound stays as the answer for a
thread whose observation recorded nothing, which is every thread until a Gmail client
supplies these.

## Proof the widened seal retains no mail text

Structural, not a promise. Every field A6 adds is an `int` or a single-line string of at
most `MAX_SEALED_SCALAR_CHARS = 64` — chosen against the values (a Gmail `internalDate` is
13 digits, a `historyId` at most 20, an RFC 3339 instant with an offset 25), not tuned. A
value over the bound is refused; a value containing `\n` or `\r` is refused outright, which
is what stops the interesting attempt — a 64-character prefix of a body is still mail text,
and the length bound alone would allow one short line per id.

Two tests carry this. `test_no_widened_seal_field_can_hold_mail_text` tries to park a real
body in each string field and in a per-id map, and exercises both refusals.
`test_the_seal_retains_nothing_but_bounded_scalars_and_the_ids_it_always_held` walks
`FetchedIds.__slots__` by reflection and asserts every retained value is a bool, an int, a
bounded single-line string, or one of the two id collections the seal has always carried —
so a **future** field of the wrong shape fails here rather than in a review six rounds on.
Removing the bound (`_sealed_scalar` returning its input) breaks **1** test.

No new write path: `python -m tools.guards` is clean including `unaudited-disk-write`, and
nothing in this change opens a file, a socket or a buffer. The seal is in-memory for the
life of one `DispositionLedger`, as it already was.

## Failing-test-first evidence

| Reintroduction | Failing tests |
|---|---|
| `_stated_total_is_the_one_the_observation_stated` → `return self` | **1** |
| `_rows_sit_at_the_position_the_observation_put_them_at` → `return self` | **2** |
| `_freshness_stamps_are_the_ones_the_observation_recorded` → `return self` | **1** |
| `_sealed_scalar` returns its input unchecked | **1** |
| `MessageRow.internal_date` / `Source.history_id` restored as parameters | **4** |

## **What A6 does not buy.** Stated plainly, and executed

A6 closes **misstatement**: a caller stating a different value for something the system
observed. It does **nothing** about **fabrication**: a caller minting an observation that
never happened states the scalar and the id together, and the envelope agrees with it
perfectly, because the thing it checks against *is* the fabrication.

`test_a6_closes_misstatement_and_does_nothing_about_fabrication` builds a wholly invented
thread — invented ids, invented positions, invented `stated_total`, invented `historyId`,
invented fetch time — discloses it, and asserts the envelope comes out with `partial=False`.
It passes. Widening the seal moved the assertion one layer down; it did not make the
assertion checkable, and nothing in this process can. That is A1's content witness in WS-13
and WS-16, and it is not built and is not mine.

---

# Part 4 — the enumeration claim

`tools/field_census.py` replaces round 7's published snippet. The round 7 script tested
`issubclass(obj, BaseModel)` and `dataclasses.is_dataclass(obj)` and **silently skipped**
anything else, so `FetchedIds` and `DispositionCertificate` — plain classes holding state in
`__slots__` — contributed 0 instead of 14, and the script produced **173** against a claim of
187.

The census reads a plain class's **own `__init__` signature**, which is the caller-facing
reading the audit table already used by hand (it lists `DispositionCertificate.token`, which
is a parameter and not a slot, and omits `FetchedIds._consumed`, which is a slot and not a
parameter). And an unrecognised class **raises** rather than being skipped: that is the
property round 7's script claimed and did not have.

* Against the round 7 field set, the corrected census gives **187 exactly** — measured
  before any of this round's A6 changes landed.
* Against this tree it gives **199**: 187 **+14** (A6's 5 new seal parameters, 2 new
  `HitOrigin` fields, 4 on `ObservedThread`, 2 new certificate parameters, 1 new ledger
  accumulator) **−2** (the two removed caller parameters).

`tests/test_field_census.py` pins the total, asserts the two previously-invisible classes are
read and read from their constructors, asserts by re-running the old reading against *this*
tree that the difference is exactly those two classes, and plants an unreadable class to
prove the census raises. Reverting the census to the round 7 reading breaks **3** tests.

---

# What I did NOT fix, and why

1. **The ordinal-date false negative** (`24th August 2026`, ProtonMail, 7 of the 28
   survivors). Closing it means teaching `_WHEN_PATTERN` a new date spelling, which puts
   "On the 24th August 2026 call, priya@example.com wrote:" — a sentence a person writes —
   inside the deletable set. A5 requires a false-positive measurement before anything new
   becomes deletable, and my corpora carry exactly one ordinal-date sentence. Declared in
   `DECLARED_FALSE_NEGATIVE_FORMATS` with the reason, and the prose sentence a future round
   must keep is already in the corpus, sitting there before the change rather than after it.
2. **The address-less attribution** (21 of 28 survivors). A5's own declared gap, unchanged.
3. **`stated_total` / `position` / `fetched_at` parameters** — checked totally, not removed.
   Reasons in the Part 3 table.
4. **`HistoryAddition.history_id`, `Counters.*`, `PoolBlock.*`, `Score.*`,
   `ScanScopeEntry.pages_fetched`, `Source.source`, `Source.withheld_here` for a non-map
   source, `GmailQueryMatch.query`/`.rung`** — every class-O and open item round 7 named and
   did not close, still open, unchanged. `Counters.http_requests` is A1's counting proxy.
5. **`ARCHITECTURE_AMENDMENTS.md`** — no entry written for the dependency removal.
   `ARCHITECTURE_DECISION.md` §D.4a carries a dated supersession note pointing here;
   `IMPLEMENTATION_PLAN.md`'s WS-07 row still names `email-reply-parser`. Both are the
   orchestrator's call, not mine to make on my own word.
6. **A1.** Not mine, not built, and Part 3's last test measures the hole it leaves.

# Where this work is weakest

**1. The latch extent — the residual false-positive class, and the honest answer to "did you
actually fix it".** Three signals have no end the client wrote: a forward separator, a
header block, and a recognised attribution line with no `>` run under it. Each removal runs
to the end of the message, so **sender-authored text written below such a block is deleted
with it**. That is the round 7 BLOCKER's own failure mode at a much smaller radius. The
round 7 stripper did the same on all three, and every corpus in this round places prose
above a quote or between two sender paragraphs — never *below an unmarked quoted block* — so
**the zero I am reporting does not cover this class**. What I did instead of hiding it:
`client_attribution_unmarked_block` is a distinct named signal, `StripResult.latched` says
when a latch happened, the `Reduction`'s detail says the extent was this stripper's
judgement rather than a boundary the client wrote, and
`test_a_latching_removal_says_so_in_its_own_result` pins the behaviour and its cost. The
real fix is to stop flattening the structure: `content/html_text.py` knows about
`<blockquote>` nesting and throws it away, and carrying it into the text form as `>` markers
would give the bounded rule the signal it needs. **That is where I would send the next
round, and a reviewer should attack this position first.**

**2. Corpus provenance.** Two of the three corpora are mine and R-ARCH's third was written
against a rule that no longer exists. A corpus is only evidence about the sentences somebody
thought of, and all three were written by people who knew what the detector does. The
strongest evidence in Part 1 is not the zero — it is the 25/200 the round 7 tree scores on
the same corpora, because that comparison is not self-graded.

**3. A6's derivation is untested against real Gmail.** Every named scalar is optional and no
production caller supplies any of them, so on this tree the exact checks never fire outside
`tests/test_sealed_scalars_a6.py` and the lower bound is still what protects real responses.
The seal's shape is a bet on what a `threads.get` will carry; the first Gmail client will
either confirm it or send this back.

**4. `_WEEKDAY_TOKENS` is a list, and lists rot.** The mask is scoped so that over-listing
is harmless and under-listing only costs a false negative, but a locale whose client emits a
weekday token not in the list *and* colliding with a pronoun reproduces R-ARCH-023 for that
locale. The seven-weekday × 23-format corpus would catch it only for the formats in it.

**5. The census pins a number, not a classification.** It proves no field is invisible to
the enumerator. It does not re-audit the 199 fields into classes D/C/O/S/I — that table is
still round 7's, minus the two rows this round removed and plus A6's, and I did not
re-derive it.
