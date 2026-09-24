# ROUND 03 — Implementer handoff (fix round)

**Implementer agent, 2026-08-31.** Scope: `docs/reviews/ROUND_03/WORK_ORDER.md`
(H1b, H2b, R-RETR-001, R-SEC-008/009/010/011/012). Nothing outside it was started: no Gmail
retrieval logic, no rungs, no ranking, no MCP surface. No rubric criterion was promoted —
`rubric_status.py --check` still reports 113 `NOT TESTED`, 0 transitions.

**Suite:** 297 → **341 tests**, all green. `make check` clean (`ruff check`,
`ruff format --check` 79 files, `mypy --strict` 61 files, `pytest -q -m "not network"`,
`python -m tools.guards`, `rubric_status.py --check`).

**Read §3 and §4 before §2.** The shortlist seal does *not* fully close H1, and the reason is
not an oversight I ran out of time on — it is a limit of what this layer can check at all.

---

## 0. What this round did, in one line

Round 2 sealed `H`'s two transport clauses and left the third asserting. R-RETR walked
through it and rebuilt R-DISC-001's dishonest 5-of-42 map end to end. H1b applies the same
inversion to the last intake, and applies it *structurally* rather than as one more check:

> `DispositionLedger._admit` is now the only writer of `self._origins`, and it takes a
> `FetchedIds`. `record_shortlist` does not call it. There is no code path in the class by
> which a shortlist can add a message id to `H` — it can only select out of it.

That is asserted by a test that reads `disposition.py` with `ast` and fails if a second
writer ever appears
(`test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page`), because the
property is about the shape of the class, not about any one input.

---

## 1. How "fails before, passes after" was verified

There is no VCS in this working copy. Each defect was **re-introduced in place** and the new
tests run against it, then the file restored and its SHA-256 compared. That is packaged as a
runnable script rather than described (session scratchpad, not shipped: it edits the tree):

```
uv run python /tmp/claude-0/-home-claude/575d70c1-c8ad-5ed4-8fc6-31be74875a3b/scratchpad/r3/regress.py   # from /root/mailweave
```

It applies six reversals, runs the tests that must catch each, restores every file
byte-for-byte (asserted, not assumed), and fails loudly if a reversal *passes* — i.e. if a
test does not discriminate. Its output for this tree:

```
== H1b/H2b  record_shortlist becomes a bare-list intake into H again
   FAILS (good)   test_the_fifty_fabricated_id_shortlist_probe_is_refused_at_intake  (+4 more)
== R-RETR-001  collapsed-run members summed naively across runs again
   FAILS (good)   test_an_id_repeated_across_two_collapsed_runs_cannot_be_built  (+2 more)
== R-SEC-008  byte-string constants invisible to the content guards again
   FAILS (good)   test_the_byte_string_bypass_registers_on_all_four_content_matching_guards (+2)
== R-SEC-009/010  no alias resolution, `.open` mode read at position 0 again
   FAILS (good)   test_a_write_reached_through_a_rebound_name_is_still_a_write (+8 more)
== R-SEC-011  Subject and attachment filename unstripped again
   FAILS (good)   test_a_bidi_override_does_not_reach_the_subject  (+2 more)
== R-SEC-012  save() no longer sweeps orphaned temp files
   FAILS (good)   test_a_temp_file_from_a_killed_save_is_swept_by_the_next_one
all reversals discriminated
```

R-RETR's own probes in `/tmp/rretr/` were run unmodified, before and after, and are quoted
per finding below. R-SEC's probe shapes were rebuilt beside `regress.py` (`probe_bytes/`,
`probe_write/{a..f}/`, `probe_fetchedids.py`) and are runnable with `uv run python -m tools.guards <dir>`.

---

## 2. Per finding

### H1b — seal `record_shortlist`

`server/src/mailweave/envelope/disposition.py`.

* `_admit(page, *, clause, rung, query)` is new and is the sole writer of `_origins`;
  `record_list_page` and `record_history_additions` delegate to it.
* `record_shortlist` refuses, **at intake**, three things: an id listed twice, an id not
  already in `H`, and more distinct ids than the declared `k`. It no longer writes
  `_origins` at all.
* `Shortlist.size` is derived from the deduplicated selection. `ledger.shortlist_ids`
  exposes what was selected; an id's `HitOrigin` still records where it *entered* `H`,
  which is the join a reviewer needs.

Why intake and not certification: at certification a fabricated id is indistinguishable
from a real one a cap dropped, so the only question left is whether a withheld note was
filed — and the attacker files the note. That is exactly how the 5-of-42 map was rebuilt.

**Before** (`/tmp/rretr/attack_h1_shortlist_hole.py`, unmodified):

```
record_shortlist accepted a bare list with ZERO transport calls: size=50
|H| is now 50, all H-sem, none backed by any FetchedIds page
```

**After**, same file:

```
DispositionInvariantError: shortlisted ids never entered H through an executed retrieval:
['fabricated-0', ... 50 ids ...]. A shortlist ranks what was fetched; it cannot introduce a
message id of its own.
```

Tests: `tests/test_disposition_invariant.py`, section "H1b". Beyond the verbatim 50-id
probe there are two that carry the impossibility claim rather than one example —
`test_no_shortlist_of_any_shape_can_grow_the_hit_set` (hypothesis, 200 examples: for *any*
sealed page and *any* caller list, either it raises or `H` is unchanged, with `k` set so the
size bound can never be what fires) and the `ast` test named in §0. Two tests that asserted
the old shape were changed, not deleted — see §3.4.

### H2b — the 5-of-42 reconstruction

**Before** (`/tmp/rretr/attack_h2_via_shortlist.py`): envelope built, `accounted_for == 42`,
37 withheld records, real evidence for 5. **After**: raises at `record_shortlist`.

`tests/test_envelope_contract.py::test_the_thirty_seven_id_map_reconstruction_is_impossible_end_to_end`
reproduces it and asserts **two** closures, because closing only the first would leave the
second as next round's finding: the shortlist refuses the ids, and if a caller files the
withheld notes anyway, `certify` refuses records for ids outside `H` ("not in H").

### R-RETR-001 — deduplicate ids across `CollapsedRun`s

`server/src/mailweave/envelope/wire.py::Source`. `collapsed_member_ids` is a new property
returning members *with* repeats so a validator can see them;
`_counts_match_the_payload` now rejects any id appearing in more than one run, counts
`collapsed_members` from the deduplicated union, and computes `present` as
`len(set(rows) | set(collapsed))`. The map-completeness error message reports the
deduplicated collapsed count.

A repeat is **rejected**, not silently collapsed: two runs claiming the same message
disagree about where it sits in the thread, and a map that cannot say where a message sits
is not a map.

**Before** (`/tmp/rretr/attack_h2_collapsed_dupe.py`): `Source` and the full envelope both
build; `included=4` meets `stated_total=4`; three distinct ids exist. **After**:
`ValidationError: messages appear in more than one collapsed run: ['d2']`.

The property test is the one that matters:
`test_a_source_that_builds_has_included_equal_to_the_messages_it_actually_holds` generates
`included` as the **naive sum** — the defect's own arithmetic — so nothing hands the source
the right answer, and asserts that either it refuses to exist or `included ==
len(disclosed_ids)`. Under the old code hypothesis finds `groups=[['a'], ['a']]` in seconds.
`test_two_collapsed_runs_over_distinct_messages_are_still_allowed` keeps segmented maps
legal, since a gate that bans them would be removed.

### R-SEC-008 — byte-string literals

`tools/guards/sweeps.py`. New `_as_text` folds `bytes` alongside `str` (UTF-8, `latin-1`
fallback so the guard cannot crash on odd bytes); `_fold` also sees through `.decode()` /
`.encode()`, which only re-spell their receiver; `_string_literals` walks `Call` nodes in
the folding pass and yields byte constants in the second.

R-SEC's probe file, unmodified — **before: 0 violations. After:**

```
ground-truth-isolation: :1: string literal references ground-truth material (ground_truth)
scope-literal:          :2: destructive harness scope 'https://mail.google.com/' ...
gmail-endpoint:         :3: path literal 'gmail/v1/users/{userId}/messages/send' ...
generative-client:      :4: string literal 'chat/completions' names a generative API path
```

All four, which is the acceptance condition stated as a set rather than as "something
fired" (`test_the_byte_string_bypass_registers_on_all_four_content_matching_guards`).

### R-SEC-009 — writes reached through a re-bound name

New `_AliasIndex` / `_build_alias_index` reads `import`s, `from`-imports and direct
`name = module.attr` assignments into a flat module-wide table; `_partial_target` reads
`functools.partial(os.write)`. All four shapes R-SEC demonstrated now report, plus the one
that was previously documented-but-uncaught:

| Shape | Before | After |
|---|---|---|
| `from os import write as w; w(fd, body)` | 0 | `w (bound to os.write)` |
| `from shutil import copy; copy(src, dst)` | 0 | `copy (bound to shutil.copy)` |
| `_writer = os.write; _writer(fd, body)` | 0 | `_writer (bound to os.write)` |
| `functools.partial(os.write)` then call | 0 | both the `partial` site and the call site |
| `import os as o; o.write(fd, body)` | 0 (documented) | `os.write` |

### R-SEC-010 — `io.open`'s mode is at position 1

`_is_write_shape` / `_classify_qualified` resolve the receiver first. For a receiver that
resolves to `io` / `_io` / `builtins` / `codecs` / `gzip` / `bz2` / `lzma`, the mode is read
at position 1; for an unresolvable receiver it is read at position 0, `pathlib`'s
mode-first signature, which is now stated in the docstring as a limit rather than implied as
coverage. `io.open("output.log", "w")` — R-SEC's exact "ordinary filename" case — goes 0 → 1
violation, and `io.open("leaked.log", "w")` is now caught for the right reason instead of by
the accident of an `a` in the filename.

This fix cuts both ways and the second direction is a **behaviour change worth reviewing**:
under the old code `io.open(p)` and `io.open(p, "r")` — ordinary reads — reported
`.open(mode=<computed at runtime>)`, because position 0 held a variable. They are now clean.
`test_resolving_the_receiver_does_not_turn_reads_into_writes` pins that, and it fails under
the reversal, so the change is deliberate and covered in both directions.

### R-SEC-011 — bidi on `Subject` and attachment filenames

* `content/headers.py::collect_headers` strips the decoded **display** value of every
  header (not just `Subject` — a display-order spoof in `From` is the same attack) and
  declares a `hidden_content` `Reduction` carrying `header=<name>` and the constructs.
* `content/mime.py::select_body` strips each `AttachmentRow.filename` and declares the same
  reduction, keyed by `part_id` — the record names the part, never the filename, so a
  reduction record does not become a second copy of what it just removed.
* `DecodedHeader.values` keeps the raw wire text unstripped: that is the unabridged path
  D.4a requires every reduction to leave, and nothing discloses it.
* `pipeline.py::_reconcile` moved to `content/reductions.py::reconcile` (public) and is now
  used by all three call sites. Headers and filenames get the same
  declared-magnitude-equals-measured-shrinkage discipline the body has; a second copy of
  that check is a second copy that can drift.

R-SEC's payload reaches `subject` and `filename` unstripped before, stripped and declared
after, with `Invoice_…` still readable. Hebrew in a subject and in a filename survives
byte-for-byte (`test_hebrew_in_a_subject_and_a_filename_survives`) — stripping RTL *letters*
would be a worse defect than the finding.

### R-SEC-012 — orphaned temp files

`auth/tokenstore.py::sweep_orphaned_temporaries()`, called at the top of `save()`. It
removes `.{name}.{pid}.{hex}` files **only** when the pid in the name belongs to no live
process (`os.kill(pid, 0)`; `PermissionError` counts as alive). A temp file whose writer is
still running is another `save()` in flight, and deleting it would cause the crash the sweep
exists to clean up after. Every error is swallowed — a credential save must not fail because
a stale file could not be removed.

The test does not synthesise the orphan. It forks, patches `Path.replace` to `os._exit(9)`
in the child so a **real** `save()` dies between fsync and replace, asserts the leftover
exists at 0600 holding the token, then sweeps it. A test that invented the filename would
keep passing if `save()`'s naming and the sweep's parsing ever drifted apart.

---

## 3. What I did not fix, and why

### 3.1 H1 is **not** fully closed. `FetchedIds` is publicly constructible.

This is the most important paragraph in the document. The work order's premise is that
`record_shortlist` was "the last unsealed intake into `H`". It was the last unsealed
*ledger method*. It was not the last unsealed intake, because the sealed page itself has an
ordinary public constructor:

```python
ledger.record_list_page(
    FetchedIds(ids=[f"fabricated-{i}" for i in range(37)], page_size=50),
    rung=RungId.L1, query="a call that never happened",
)
# -> |H| == 37, and record_shortlist then accepts all 37, because they are in H
```

That is R-RETR's fabrication, one call to the left, in two lines. Verified in this tree
after the fix.

**I did not close it, and I do not believe it is closeable at this layer.** A page's
provenance is the assertion "I executed this call", and the only code that can make that
assertion is the Gmail wrapper that really does execute it — so any constructor the real
wrapper can reach, a fake one can reach. Putting the constructor behind a capability token
would change *who has to reach for a private name* (moving it into the same category as
`_MINT_TOKEN` and `_RECORD_TOKEN`) without changing what is possible; shipping that and
calling it a seal would be exactly the over-claiming the standing rule forbids. Inverting
the fetcher contract so the transport seals raw ids relocates the same trust boundary.

What actually makes the claim checkable is a witness **outside the process**, and the plan
already has one: `IMPLEMENTATION_PLAN.md` WS-13's "counter cross-check against the harness
counting proxy on `http_requests`". Until that lands, `|H|` is bounded below by what the
transport fetched and bounded above by nothing.

Handled honestly rather than quietly: `FetchedIds`'s docstring now states the direction it
does *not* bound, and
`test_a_hand_built_page_is_accepted_and_that_is_the_documented_residual` asserts both the
gap and the docstring, so neither can drift unnoticed. R-RETR should decide whether this
reopens H1 as a finding; my own read is that it does, at MEDIUM, and that EV-01 stays
NOT YET PASS on it.

### 3.2 H-sem is now a subset of H-lex ∪ H-hist. That is a spec deviation, deliberately.

AD A.7a defines `H` as the union of three clauses. Under this seal the third is a
*selection* over the first two, not an independent source. For the pool MailWeave actually
builds the union is unchanged — A.7a itself routes the L5 participant probes through H-lex
("`messages.list` calls like any other") — so what is forbidden is only the case A.7a never
contemplated and R-RETR exploited: shortlisting an id no executed retrieval returned.

**The consequence lands on WS-08, so it should not be discovered there.** If pool
construction ever produces a candidate outside both sealed clauses — a `threads.get`
expansion, say — `record_shortlist` will refuse it, and the right fix is a sealed intake for
that source, not a relaxation here. If the owner disagrees, this is an amendment to A.7a,
not an implementation detail. Recorded in `disposition.py`'s module docstring.

### 3.3 Narrower residuals I chose not to chase

* **The shortlist's *composition* is still the caller's claim.** Provenance and size are
  derived; *which* of `H`'s ids were ranked is not checkable here. It is harmless for
  evidence preservation — an unshortlisted id stays in `H` and must still be accounted for —
  but `retrieval_report.shortlist` remains a report about ranking, not a verified one.
* **The same id as a row in two different `Source`s** is not checked. It cannot inflate a
  map (a `WithheldRecord` carries one `thread_id`, and `_notes` is keyed by message id, so an
  id backs exactly one source's map) and it is a nonsense claim rather than a loss, but I did
  not verify it exhaustively and it is not filed. Flagging it for R-RETR rather than
  claiming it clean.
* **NBSP → space substitution is not declared as a reduction**, in the body path (pre-existing)
  or in the two paths I added. It preserves length, so `reconcile` cannot see it. Small, real,
  and out of this work order.
* **R-SEC-004 / SEC-07** untouched, as the work order says.

### 3.4 Two existing tests were changed

Both asserted the shape H1b removes, so leaving them would have meant leaving the bug.
`test_participant_probes_and_history_additions_enter_the_hit_set` now shortlists an id the
L5 probe returned (clauses are `{H-lex, H-hist}`; `shortlist_ids` asserted separately), and
`test_a_shortlist_without_a_declared_pool_is_refused` fetches its id first.
`test_a_shortlist_larger_than_its_declared_k_is_refused` was *strengthened*: its ids are now
in `H` and it matches on `"exceeds the declared k=3"`, because otherwise the new provenance
check would have satisfied it and the `k` bound would have gone untested — a tautology that
would have looked like a pass.

---

## 4. Where this work is weakest

Ranked, most likely to be a real problem first.

1. **§3.1.** The headline fix closes one of two doors into the same room. Every claim in §2
   about H1b is true and none of it makes `H` unfabricable. If the round is graded on
   "H1 closed", it is not.
2. **The alias index is flat and scope-blind.** `_build_alias_index` walks the whole module
   and ignores shadowing, re-binding and function scope. A local `copy = my_own_copier`
   anywhere in a file makes every later `copy(...)` in that file report as `shutil.copy`.
   That errs toward reporting, which is the right direction for a gate, but it is a false
   positive a future refactor can trip, and a gate that cries wolf is a gate that gets
   disabled. Documented in the guard's own "Does not catch"; not otherwise mitigated.
3. **Byte-string folding widens what the content guards read.** Any `bytes` literal in
   server code is now matched against the forbidden markers, so a future embedded blob that
   happens to contain `manifest` or `chat/completions` is a violation with no evasion behind
   it. Related and uglier: `_fold` will happily concatenate a `str` and a `bytes` operand
   into text Python itself would reject, so a nonsense expression could in principle produce
   a match. Neither occurs in the tree today; both are cost I accepted for closing R-SEC-008.
4. **`test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page` is a source
   reader.** It is the strongest evidence in the round *and* the most brittle: it recognises
   mutation as `self._origins[...] = ...`, an augmented/annotated assign, `del`, or a call to
   one of six dict mutators. A writer that mutates `H` some other way — through a local alias
   to the dict, say — passes it. It proves "no second writer of this shape", not "no second
   writer".
5. **The R-SEC-012 test forks.** `os.fork` inside pytest is the only way I found to produce
   a genuine post-fsync kill in-process, but it is the test most likely to behave differently
   on another runner. If it is ever skipped, R-SEC-012's evidence goes with it.
6. **`reconcile` moved modules.** `content/reductions.py` now imports `mailweave.errors`,
   which is a new edge in the content package's dependency graph. It is acyclic today
   (`errors` imports nothing from `content`) and `mypy --strict` is clean, but it is churn
   that was not asked for, taken to avoid a third copy of the same check.
7. **I did not re-run R-DISC's or R-ARCH's round-1 probes.** Regression evidence for what
   earlier rounds closed is the 341-test suite plus R-RETR's own files, not a fresh
   adversarial pass over their findings.
