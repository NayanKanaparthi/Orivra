# ROUND 02 — Implementer handoff (fix round)

**Implementer agent, 2026-08-31.** Scope: `docs/reviews/ROUND_02/WORK_ORDER.md` (H1–H6, M1–M3).
Nothing outside it was started: no Gmail retrieval logic, no rungs, no ranking, no MCP surface.

**Suite:** 199 → **297 tests**, all green. `make check` clean (`ruff check`, `ruff format --check`,
`mypy --strict` 61 files, `pytest -q -m "not network"`, `python -m tools.guards`,
`rubric_status.py --check` = 113/113 `NOT TESTED`, 0 transitions). No rubric criterion was
promoted; that is a reviewer's job.

---

## 0. The one thing this round did

Round 1 closed the gap in one place: `withheld := H − disclosed`, a set difference. Every other
site in this round had the same shape — a claim computed *beside* the enumeration it describes,
free to drift from it. Each fix below is that same inversion, not nine separate patches:

| Site | The claim | Now derived from |
|---|---|---|
| H1 | `H`, the hit set | the pages the transport actually fetched (`FetchedIds`, sealed) |
| H2 | `map_id`, "this is the thread's map" | rows + collapsed-run members + backed withheld records |
| H6 | `truncated_by: mailweave` | the measured size of the assembled payload, plus the ladder artifacts in it |
| M1 | `reductions[].removed_chars` | the pipeline's own before/after measurement of each stage |
| H4 | "markup removed, text retained" | the bound applied before the parse, counted |
| H3 | "this guard catches X" | what the guard demonstrably catches, with an explicit "Does not catch" |

---

## 1. How the before/after evidence was produced

There is no VCS in this working copy, so "the test fails before the fix" was verified by
**re-introducing each round-1 defect in place and running the new tests against it**, then
restoring the file and checking its SHA-256 matches. The harness lives in this session's
scratchpad (`.../scratchpad/r2/regress.py`), not in the repo — it edits source in place and
is not something to ship — and its output is quoted verbatim below. Re-running it is a
matter of re-applying the reversals listed in it; the probe scripts beside it
(`before_h1_h2_h6.py`, `after_h1_h2_h6.py`, `measure_h5.py`, `h4_numbers.py`) are
self-contained and need only `PYTHONPATH=/root/mailweave`.

```
finding                           result with the round-1 defect re-introduced
H1 transport owns recording       3 failed, 6 passed   first failure: test_a_fetched_page_has_no_public_member_that_yields_an_id
H2 map completeness               3 failed, 2 passed   first failure: test_a_claimed_map_that_omits_most_of_the_thread_is_unconstructible
H3 guard hardening               12 failed, 30 passed  first failure: test_the_round_one_bypass_files_no_longer_pass_the_guards
H4 html bounds                    6 failed, 4 passed   first failure: test_nesting_is_flattened_to_the_cap_before_any_parser_sees_it
H5 quote classification           9 failed, 33 passed  first failure: test_the_reply_survives_and_the_chain_does_not[signature_no_delimiter]
H6 self-truncation verified       4 failed, 3 passed   first failure: test_an_oversized_response_fails_assembly_rather_than_being_shipped
M1 reduction magnitude            1 failed, 12 passed  first failure: test_a_stripper_that_under_reports_its_removal_fails_the_pipeline
M2 atomic token write             2 failed, 2 passed   first failure: test_a_crash_during_the_write_never_leaves_the_token_in_a_readable_file
M3 bidi controls                  3 failed, 1 passed   first failure: test_a_bidi_override_does_not_reach_body_clean[text/plain]

all files restored; running the suite clean: 297 passed
```

**Read the H1 line honestly.** The reversal there could only remove the *seal* (`FetchedIds`
became readable and `record_list_page` accepted a bare list); it could not un-build the
transport, so 6 of the 9 seam tests still passed. H1's true "before" is the reviewer's probe,
re-run against round-1 code before any change:

```
H1: built OK. |H|=10 disclosed=10 withheld=0 unaccounted=90
H2: Source(map_id='map-t1-full') built OK: stated_total=42 included=5 collapsed_runs=0
    -> 37 messages represented nowhere
H6: built OK. truncated_by='mailweave' measured=27000 ceiling.applied=9000 rows_reduced=0
```

and after:

```
H1: transport returned RecordedListing fields=['ids_recorded','next_page_token','scan_scope']
    ids_recorded=100 |H|=100;  opening a page without the ledger's token -> DispositionInvariantError
H2: ValidationError: source t1 claims map_id='map-t1-full' but accounts for 5 of 42 messages
    (5 rows + 0 collapsed + 0 withheld); 37 are represented nowhere.
H6: ResponseCeilingExceeded: assembled response is ~27000 whitespace tokens against an applied
    ceiling of 9000; declaring self-truncation does not make it fit.
```

---

## 2. Per finding

### H1 — the transport owns ledger recording (R-ORCH-001, R-ARCH-005)

**Changed.** `envelope/disposition.py` gains `FetchedIds`: the IDs one executed transport call
returned, with no `ids` property, no `__iter__`, no `__getitem__`. Its public surface is
`size`, `page_size`, `more_pages`, `next_page_token`, `recorded` — counts and an opaque
continuation token. It opens only through `_release(_RECORD_TOKEN)`, and `DispositionLedger`
holds the token. `record_list_page` and `record_history_additions` now take a page, not an
`Iterable[str]`, and read `ids_returned` / `page_size` / `more_pages` off the page so a caller
cannot describe a page as smaller than the one that entered `H`.

New package `mailweave/retrieval/` holds the seam WS-02 will use:
`RecordingListTransport.list_messages(ledger, ...) -> RecordedListing`. The fetch and the
ledger write are one call; the return value carries a `ScanScopeEntry`, a count and a page
token, and no message ID.

**Tests** (`tests/test_transport_seam.py`, 9): the probe rewritten (fetch 100, disclose 10 →
`DispositionInvariantError` naming `real-hit-50`); the returned object's every reachable member
asserted disjoint from the fetched IDs; `_release` with a foreign token refused *and* with the
real token accepted, so the refusal is a capability check rather than a dead function; a bare
list rejected by both ledger entry points; a fetcher returning a list rejected by the transport;
and a hypothesis property (200 examples) that `H` equals the union of every page fetched no
matter how few IDs a hostile caller wants to keep.

**Limits, stated.** Python cannot seal an attribute: `page._ids` is reachable by a caller who
reaches for a private name, the same narrow exception `disposition.py` already documents for
`_MINT_TOKEN`. And a caller that *holds the raw fetcher* can call it and decline to record —
no IDs escape (the page is unreadable) but those messages never enter `H`. That obligation is
written into `retrieval/transport.py`'s docstring as WS-02's to keep: construct the transport
inside the client, keep the fetcher private, never return `list[str]`.

### H2 — a claimed map accounts for every message (R-DISC-001)

**Changed.** `wire.py::Source` gains `withheld_here: tuple[str, ...]` and two validators.
`accounted_for` = rows + collapsed-run members + distinct `withheld_here`. When `map_id` is set,
`accounted_for` must equal `stated_total`; the error names the shortfall and the three
dispositions. A message may not be both present and in `withheld_here`.
`response.py::Envelope` cross-checks `withheld_here` against the withheld records the response
actually carries — an id nothing withholds raises `DispositionInvariantError`, and for a map
source the two sets must match exactly. So the map claim cannot be closed by an assertion; it is
closed by the enumeration or not at all. A `Source` *without* `map_id` is a search view and
carries no such obligation — the distinction the schema previously could not express.

**Tests** (in `test_envelope_contract.py`): R-DISC-001's exact shape now unconstructible; the
same source without `map_id` still legitimate (a gate that refused the normal case would be
removed); all three dispositions accepted and one-short refused; the fictitious withheld record
refused at envelope level; present-and-withheld refused.

### H3 — the six AST guards (R-SEC-001)

**Both halves done: hardened, and the claims narrowed.**

Hardening in `tools/guards/sweeps.py`: string constants are **constant-folded** before matching
(`ast.BinOp(Add)` chains and f-strings, with interpolations folded to `{}`), so a split literal
is no longer invisible; endpoint paths are compared with placeholders normalised, so
`f"gmail/v1/users/{uid}/messages"` stays legal while `.../messages/send` does not;
`importlib.import_module` / `__import__` are read as imports, and a dynamic import whose module
name cannot be read statically is itself a violation; the write guard gained `.open(...)` on any
receiver (mode-aware — `Path.open`'s mode is the first argument, the builtin's is the second),
`os.write`, `os.open`, `os.fdopen`, `os.replace/rename/link/symlink`, `shutil.copy*`/`move`,
the `tempfile` factories, and `pickle`/`marshal` `dump`. An `open` whose mode cannot be
evaluated is reported rather than assumed to be a read.

Narrowing: the module docstring now states what **no** guard here can catch (`eval`/`exec`,
names read from files or the environment, `getattr` chains, C extensions), and every guard
carries an explicit **"Does not catch"** paragraph. A test asserts that paragraph exists for
each registered guard, so a future guard cannot be added without bounding its claim.

**Evidence.** R-SEC-001's four demonstration files are now repo fixtures in `test_guards.py`.
Round 1: `run_all()` → **0 violations**. Round 2: **11 violations, all six guards firing**, with
each bypass shape asserted against the guard it defeated. The shipped tree stays clean, and
tests assert the legitimate shapes still pass (a dynamic import of `json`, a read-mode
`Path(p).open()`, an f-string of a declared endpoint).

Also fixed: `python -m tools.guards <dir outside the repo>` crashed in `relative_to` while
*reporting success* — the exact command a reviewer runs to reproduce R-SEC-001.

### H4 — HTML depth and size bounds (R-SEC-002)

**Changed.** `bound_markup()` runs before either parser. Source over `HTML_SOURCE_CHAR_CAP`
(2,000,000 chars) is truncated at a tag boundary and counted; markup nested deeper than
`HTML_DEPTH_CAP` (64) is **flattened — the tags go, the text inside them stays**, so the depth
bound removes markup and not content. Both counts ride on `HtmlExtraction` and the pipeline
declares them as `html_size_cap` / `html_depth_cap` reductions with character counts and the
deepest nesting seen.

Measured, same box, same inputs (`scratchpad/r2/h4_numbers.py`):

| nested tags | round-1 selectolax | round-2 | round-1 lxml | round-2 lxml |
|---|---|---|---|---|
| 10,000 | 0.31 s → `'hi'` | 0.03 s → `'hi'` | 0.01 s → **`''`** | 0.02 s → `'hi'` |
| 40,000 | 4.55 s → `'hi'` | 0.10 s → `'hi'` | 0.00 s → **`''`** | 0.10 s → `'hi'` |
| 100,000 | 30.06 s → `'hi'` | 0.25 s → `'hi'` | 0.00 s → **`''`** | 0.25 s → `'hi'` |
| 200,000 (~1 MB body) | **122.36 s** → `'hi'` | **0.47 s** → `'hi'` | 0.00 s → **`''`** | 0.47 s → `'hi'` |

The silent lxml drop is gone at every depth measured, because the bound puts the tree inside
lxml's own nesting limit rather than because of a cap declaration.

**Silent loss, second half.** A parse that consumes visible text and produces none now sets
`lost_text_chars`, and the pipeline declares an `html_parse_lost_text` reduction with the count;
emptiness explained by a removed hidden construct is not counted as loss. I first implemented
this as a `ContentProcessingError` (R-SEC's other permitted option) and **backed it out**: a
4,000-case fuzz found 11 malformed-but-plausible documents (stray doctypes, unbalanced tags,
control characters) where both parsers legitimately recover nothing, and turning those into a
hard error would fail whole messages over formatting. A declared reduction is equally honest and
does not lose the message. A hypothesis property in the suite now asserts that no document
yields an empty body without either a hidden-construct removal or a declared loss.

**Bonus defect found and fixed by that property:** `_extract_lxml` crashed with an untyped
`ValueError` out of `dict(node.attrib)` when an attribute name held a control character
(`"<" + "A " + "\x1f" + "<div>…"`). Pre-existing, not introduced here; now caught, with the
consequence stated in place (style-based hiding on *that node* cannot be inspected).

### H5 — quote stripper (R-ARCH-001, R-ARCH-002)

**Changed.** Classification is derived from each fragment's shape and position instead of the
parser's `hidden` flag: `looks_quoted()` recognises attribution lines, `-----Original
Message-----` / forward separators, two-or-more Outlook header lines, and `>` markers; a latch
records that the quoted chain has begun, so the *body* of an Outlook block (which carries no
marker of its own) is quoted rather than signature; a fragment the parser recognised as a
delimited signature keeps that classification wherever it sits, **unless** it looks like a quote
header — which is what separates a real `-- ` signature below a quote from
`---------- Forwarded message ---------`, both of which trip the parser's delimiter heuristic.
A conservative undelimited-signature detector then removes trailing `Best regards,` / mobile
sign-off blocks: it requires body text above, at most 6 short lines below, and no long line.

**Corpus and measurement.** `tests/fixtures/reply_chains.py` — 13 synthetic cases covering the
shapes R-ARCH used (Gmail top-post, Outlook header block, `-----Original Message-----`,
forwarded, mobile signature, 4-level nesting, `--`-delimited signature, undelimited signature,
undelimited signature above a quote, bare `>` with no attribution, a `>` that is arithmetic,
HTML Gmail blockquote, French attribution). Every byte invented here; nothing sanitised from any
mailbox. `leaked` = characters that should have been removed and stayed in `body_clean`;
`lost` = characters that should have been kept and were removed.

```
case                                 BEFORE                          AFTER
                                     quoted  sig leak lost           quoted  sig leak lost
gmail_top_post                          179    0    0    0              179    0    0    0
outlook_header_block                      0  247    0    0  MISLABEL    247    0    0    0
original_message_separator                0  199    0    0  MISLABEL    199    0    0    0
forwarded_message                         0  225    0    0  MISLABEL    225    0    0    0
mobile_signature                        107   19    0    0              107   19    0    0
four_level_nesting                      336    0    0    0              336    0    0    0
signature_with_delimiter                  0   65    0    0                0   65    0    0
signature_no_delimiter                    0    0   72    0  LEAK          0   94    0    0
signature_no_delimiter_after_quote      116    0   31    0  LEAK        116   35    0    0
bare_quote_no_attribution                74    0    0    0               74    0    0    0
greater_than_in_prose                     0    0    0    0                0    0    0    0
html_gmail_blockquote                     0  115    0    0  MISLABEL    115    0    0    0
french_attribution [known gap]           49    0   28    0               49    0   28    0

clean (no leak, no loss, correct kind): BEFORE 6/12 asserted → AFTER 12/12 asserted
mislabelled cases 4 → 0; leaked signature characters 103 → 0; content lost 0 → 0
```

The French case is **not fixed** (R-ARCH-003, a tracked MEDIUM outside this work order). It is in
the corpus as a declared `known_gap`, asserted to still behave exactly as measured — the quoted
body goes, the `a écrit :` line stays — so it cannot quietly change without a test noticing.

### H6 — `mark_self_truncated()` verifies shrinkage (R-DISC-002)

**Changed.** `measure_tokens` moved to `envelope/measure.py`, and the ceiling is now enforced
**inside `Envelope`**, not by the builder: a response over `ceiling.applied` raises
`ResponseCeilingExceeded` whether or not it claims truncation, and a `truncated_by` claim with no
ladder artifact in the payload (no collapsed run, no stub/snippet row, no `body_head_truncated`
reduction, no `disclosed_token_ceiling` withheld record, no split-off source) is refused.
`mark_self_truncated()` now sets a declaration and buys no exemption; its docstring says so.

**Tests:** R-DISC-002's shipment (27,000 tokens against 9,000, flag set, nothing cut) raises; a
flag with nothing removed raises even *under* the ceiling; an oversized response is refused in
both directions (with and without the flag) so the check cannot be satisfied by dropping the
declaration; and a truncation backed by a real head-truncation reduction still builds.

### M1 — declared magnitude matches actual shrinkage (R-ARCH-004)

`pipeline._reconcile(stage, before, after, declared)` compares each stage's declared removal
against the shrinkage the pipeline itself measured, and raises `ContentProcessingError` naming
both numbers otherwise — `certify`'s shape applied to characters. It covers the quote/signature
stage (all three counts summed), normalisation and head truncation; the HTML stage's
`html_to_text` count is now recomputed from the pipeline's own `len(text)` rather than taken
from the extractor's self-report. R-ARCH's monkeypatch (remove 220, declare 1) now fails with
`declared 1 removed characters but the text shrank by 220 (245 -> 25)`. Added: an exact
end-to-end equality test on the fixture, and a hypothesis property that declared removals never
*understate* shrinkage (one-sided for HTML, which legitimately double-counts hidden text).

### M2 — `TokenStore.save()` is atomic (R-SEC-003)

Write to `.credentials.json.<pid>.<rand>` in the 0700 directory with `O_EXCL` (so the mode is
honoured — there is no existing file to inherit from), `json.dump`, `flush`, `os.fchmod`,
`fsync`, verify the mode, then `Path.replace` onto the final path; on any exception the temp
file is unlinked. The final path is only ever replaced whole.

Reproduction, before: pre-existing `0644` file + a crash between write and chmod →
`mode=0644 secret_on_disk=True`. After: the same crash leaves the refresh token in no readable
file at all, and the tests assert it directory-wide (every leftover, not just the target path),
that no temp file survives a failure, and — by observing the rename — that at the moment of
replacement the destination still holds the old content.

### M3 — unicode bidi overrides (R-SEC-005)

`strip_invisible_characters()` (shared by the HTML extractor and the pipeline) removes
U+202A–U+202E, U+2066–U+2069 and U+200E/U+200F alongside the zero-width set, counting each class
separately; `HiddenConstruct.BIDI_OVERRIDE` is declared in a `hidden_content` reduction with the
count. Applied to `text/plain` as well as HTML — round 1's `normalise(rlo).text == rlo` was
`True`, i.e. the spoof reached `body_clean` byte-for-byte. Tests cover both body types, the full
control set, and that ordinary right-to-left *text* (Hebrew) is untouched — removing letters
would be the worse defect.

---

## 3. What I did NOT fix, and why

- **R-ARCH-003, non-English attribution lines.** Out of this work order (tracked MEDIUM). Now
  measured and pinned as a declared `known_gap` in the corpus instead of being unmentioned.
- **R-SEC-004, `check_url` raising `idna.InvalidCodepoint` instead of `EgressBlocked`.** Not in
  the work order; fails closed. Untouched.
- **R-ARCH-006, no guard against raw `httpx.Client()`.** Not in the work order. Adding a seventh
  guard would have meant adding a claim this round was not asked to verify. Untouched.
- **R-DISC-003 (wire field order), R-DISC-004 (8 untested `Reason.render()` variants, the OD-3
  parent/child-stub shape), R-DISC-005 (`fetched_at` accepts any string), R-DISC-006
  (`constraint_coverage` placeholder), R-SEC-006/007 (payload-size and deep-nesting robustness in
  `payload.py`).** All carried, all out of scope.
- **`DispositionLedger.record_shortlist` still takes a bare `Iterable[str]`.** Deliberate, and
  the weakest spot in H1's story — see below.
- **No rubric criterion marked PASS**; `rubric_status.py --check` still reports 113 `NOT TESTED`,
  0 transitions.

Two things I changed that were *not* asked for, both small and both stated so a reviewer can
reject them: `docs/reviews/**` is now excluded from `ruff format` and `format-check` is folded
into `make check` (R-ARCH-007 — `ruff format .` had silently rewritten Python inside R-SEC.md's
and R-ARCH.md's fenced blocks during this round; I restored both files byte-for-byte); and the
guards CLI no longer crashes on an out-of-repo target.

## 4. Where this work is weakest

1. **`record_shortlist` is the hole in H1.** H-lex and H-hist are sealed; H-sem is not. A caller
   can still hand the ledger a shortlist of IDs it chose. I did not seal it because the shortlist
   is a *local ranking* over a pool, not a transport fetch, and the honest constraint — "every
   shortlisted ID came from a recorded pool" — needs WS-08's pool to exist. Today a rung that
   under-records at L5 is still possible. This is the first thing a reviewer should attack.
2. **The seal is a convention plus a token, not a capability system.** `page._ids` is reachable;
   so is `_RECORD_TOKEN`. I claim only what `disposition.py` already claims for `_MINT_TOKEN`.
   Whether that is enough is a judgement call I have made explicit rather than settled.
3. **H2 adds a wire field.** `withheld_here` is a second place a thread's withheld set is named.
   I cross-check it against `Envelope.withheld` so it cannot diverge silently, but the honest
   description is "derived-and-verified", not "derived". A design where `Source` could read the
   response's withheld records directly would need no field; the schema does not allow it.
4. **`HTML_DEPTH_CAP = 64` and `HTML_SOURCE_CHAR_CAP = 2,000,000` are engineering bounds I chose.**
   They are not `[UNSET — register at G0]` values and no criterion is measured against them, and
   `constants.py` says so — but I have no corpus of real HTML mail to show that 64 is above the
   deepest legitimate newsletter table. If a reviewer thinks that number needs registering rather
   than choosing, they are entitled to that.
5. **H5's undelimited-signature detector is a heuristic with an English sign-off list.** It is
   conservative (body above, ≤6 short lines below), and the corpus contains two false-positive
   traps that pass, but 13 synthetic cases are not a measurement of real mail. GMAIL-02 still
   needs a real-mailbox sample, and R-ARCH's verdict that the `email-reply-parser` substitution is
   "a quality regression the project must track" still stands.
6. **`measure_tokens` remains a whitespace estimate.** H6 now enforces the ceiling against it, so
   the ceiling is exactly as good as that estimate until the G0 tokenizer is pinned. Every use
   still names it an estimate.
7. **The `_tag_spans` scanner used by `bound_markup` is cruder than the parsers it protects.** An
   attribute value containing a literal `>` ends a token early, which makes the depth estimate
   conservative — never unbounded, but it can flatten slightly more markup than strictly needed
   and count it. Stated in the function's docstring.
8. **The defect-injection harness proves each test fails against a *reconstructed* defect, not
   against the original round-1 tree.** For H1 in particular the reconstruction is partial
   (6 of 9 tests still pass under it). The probe outputs in §1 are the primary evidence there.

## 5. Files

New: `server/src/mailweave/retrieval/{__init__,transport}.py`,
`server/src/mailweave/envelope/measure.py`, `tests/test_transport_seam.py`,
`tests/test_quote_corpus.py`, `tests/fixtures/reply_chains.py`.

Changed: `envelope/{disposition,wire,response,builder,__init__}.py`,
`content/{quotes,html_text,pipeline,reductions}.py`, `auth/tokenstore.py`, `constants.py`,
`tools/guards/{sweeps,__main__}.py`, `tests/{test_envelope_contract,test_guards,
test_content_units,test_content_pipeline,test_auth_and_config,test_disposition_invariant,
test_disposition_property,test_envelope_serialisation,test_outcome_od2,
test_invariant_under_optimised_python}.py`, `tests/fixtures/envelope_kit.py`, `Makefile`,
`pyproject.toml`.

Restored after an accidental `ruff format` rewrite: `docs/reviews/ROUND_01/R-SEC.md`,
`docs/reviews/ROUND_01/R-ARCH.md`.
