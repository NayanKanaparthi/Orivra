# ROUND 04 — Implementer handoff (fix round)

**Implementer agent, 2026-08-31.** Scope: `docs/reviews/ROUND_04/WORK_ORDER.md` —
R-RETR-002, R-RETR-004/amendment A2, R-SEC-013, R-SEC-014, R-SEC-015, R-SEC-016. Nothing
outside it was started: no Gmail retrieval logic, no rungs, no ranking, no MCP surface,
**and no A1**. No rubric criterion was promoted and no row was added to
`RUBRIC_TRANSITIONS.md`; `rubric_status.py --check` still reports 9 PASS / 104 NOT TESTED /
9 reviewer transitions, unchanged from the state Round 3 left.

**Suite:** 341 → **406 tests**, all green. `make check` clean (`ruff check`,
`ruff format --check` 87 files, `mypy --strict` 61 files, `pytest -q -m "not network"`,
`python -m tools.guards`, `rubric_status.py --check`).

**Read §5 before §3.** Two of these fixes changed a signature that Round 3's probes call,
and §6 is where this round is weakest — the largest hole in the guard family is *still*
open by design, and it is bigger than any of the four findings that were closed.

---

## 1. How "fails before, passes after" was verified

There is still no VCS in this working copy. Each defect was **re-introduced in place** and
the tests that must catch it run against it, then the file restored and its SHA-256
compared with the value taken before the edit. Packaged as a script (session scratchpad, not
shipped — it edits the tree):

```
uv run python /tmp/claude-0/-home-claude/575d70c1-c8ad-5ed4-8fc6-31be74875a3b/scratchpad/r4/regress.py
```

It begins with a **control run**: every listed test is run against the *unedited* tree and
must pass, so a harness that reports "fails" because of a broken invocation is caught rather
than believed. Its output for this tree:

```
control: every listed test passes against the unedited tree

== R-RETR-002  collapsed runs compared by member id only, never by position
   FAILS (good)  test_two_collapsed_runs_cannot_claim_the_same_thread_positions  (+4 more)
== R-RETR-004 / A2 (clause)  H-thr removed: threads.get is not a clause and has no intake
   FAILS (good)  test_a_shortlist_may_select_a_threads_get_candidate  (+4 more)
== R-RETR-004 / A2 (endpoint match)  an intake accepts an observation of any endpoint
   FAILS (good)  test_each_intake_admits_its_own_endpoint_and_no_other[messages.list-history.list]  (+5 more)
== R-SEC-013  fold reads only Constant/BinOp(Add)/JoinedStr/.decode, absorbs while descending
   FAILS (good)  test_each_constant_obfuscation_idiom_is_folded_before_matching[format]  (+8 more)
== R-SEC-014  an Attribute call's receiver is resolved through module aliases only
   FAILS (good)  test_a_write_through_a_class_attribute_is_caught
== R-SEC-015  one flat table for the whole module, first resolvable binding wins
   FAILS (good)  test_a_local_name_reused_in_another_function_is_not_reported[reused_local_name]  (+4 more)
== R-SEC-016  the five-module opener allowlist, no constructors, no dbm flags
   FAILS (good)  test_a_resolved_opener_is_read_at_the_mode_position_whatever_the_module_is[dbm]  (+9 more)
all reversals discriminated
```

Seven reversals for six findings: A2 is reversed twice, because it makes two independent
claims (a new clause, and an intake that refuses an observation of the wrong endpoint) and a
single reversal would have let either half ride on the other.

---

## 2. Files changed

| File | Finding |
|---|---|
| `server/src/mailweave/envelope/wire.py` | R-RETR-002 |
| `server/src/mailweave/envelope/disposition.py` | A2 |
| `server/src/mailweave/envelope/__init__.py` | A2 (one export) |
| `server/src/mailweave/retrieval/transport.py` | A2 (the `threads.get` seam) |
| `tools/guards/sweeps.py` | R-SEC-013/014/015/016 |
| `docs/ARCHITECTURE_DECISION.md` | A.7a gains the `H-thr` clause, pointing at A2 |
| `tests/…` (6 files, incl. `fixtures/envelope_kit.py`) | the tests below |

---

## 3. Per finding

### R-RETR-002 — one position, one disposition

`server/src/mailweave/envelope/wire.py`, new validator
`Source._one_position_holds_one_disposition`.

R-RETR-001 was closed at the level of *identity*: a message may not appear in two collapsed
runs. R-RETR-002 is the same defect at the level of *place*, and the id check cannot see it —
two runs whose members are entirely disjoint are never compared. The occupancy of each thread
position is now computed from the payload: a position is claimed by a row **or** by one
collapsed run, never twice.

Rows are included, not only runs. A stub row at position 4 and a run spanning 3–6 make
contradictory claims about slot 4, and checking runs against each other while ignoring rows
would have left the same arithmetic hole one disposition to the left.

**Before** (R-RETR's shape, run against the round-3 tree):

```
BUILT: included=10  accounted_for=10  stated_total=10
positions: [(1, 5), (1, 5)]
```

**After**, same input:

```
ValidationError: two dispositions claim the same thread position in source t1:
position 1: collapsed run (1, 5) and collapsed run (1, 5); … and 1 more. A message has one
position and one disposition (A.7a) … (PART-05, R-06, R-RETR-002)
```

Tests (`tests/test_envelope_contract.py`, section "R-RETR-002"): the verbatim two-run shape;
a partial overlap ((3,5) vs (5,7)) so the fix is not read as "identical ranges only"; the
row-vs-run clash; **R-RETR's end-to-end reproduction** — a real ledger with one real fetch
backing `run_a`, nothing backing `run_b`, and the full `map_id`-bearing
`EnvelopeBuilder.build()` — and a hypothesis property.

The property test is the one that matters. R-RETR-001's generator advanced `start` by each
group's own length, so it could never emit an overlap; this one draws `(start, size)` pairs
independently and mints member ids per run, so ids are distinct by construction and the *only*
variable is where each run begins. It asserts: either the source refuses to exist, or the
number of distinct positions it occupies equals the number of messages it claims to
enumerate. The refusal branch asserts the refusal was deserved, so "reject everything" does
not pass it. Under the old code there was a third outcome — it built, and a map claimed ten
messages across five slots.

### R-RETR-004 / amendment A2 — a sealed observation, and `H-thr`

`server/src/mailweave/envelope/disposition.py`, `retrieval/transport.py`.

The seal now takes a sealed **observation** carrying the endpoint that produced it:

* `ObservedEndpoint` — `messages.list` / `history.list` / `threads.get` — and
  `CLAUSE_BY_ENDPOINT`, which maps each to `H-lex` / `H-hist` / `H-thr`;
* `FetchedIds` keeps its name and gains a **required** `endpoint`. The pagination fields are
  optional and endpoint-checked at construction: a `messages.list` observation must carry the
  page size `scan_scope` will report, a `threads.get` observation must name its thread, and
  neither invents a field the call did not have;
* `_admit` derives the clause from `observation.endpoint` instead of taking it as an argument,
  and refuses an observation whose endpoint is not the one that intake is for;
* `DispositionLedger.record_thread` and `RecordingListTransport.get_thread` are the new
  intake and the new seam.

**The single-writer property survives, and each half of it was checked, not assumed:**

* `_admit` is still the **only** writer of `self._origins`.
  `test_the_hit_set_has_exactly_one_writer_and_it_demands_a_sealed_page` — the `ast` test —
  passes unmodified; it is the test that would fail if `record_thread` had written `_origins`
  itself, and it also still asserts that the one writer's signature names `FetchedIds`;
* only sealed observations are admitted. `record_thread` is included in
  `test_the_ledger_does_not_accept_a_bare_id_list`, so all three intakes are shown to reject
  a bare list, and the transport refuses a fetcher that returns one;
* there is no new path that accepts an unsourced id.
  `test_no_shortlist_of_any_shape_can_grow_a_hit_set_built_from_all_three_clauses` re-runs
  H1b's impossibility property with `H` accumulated across all three endpoints at once: for
  any observations and any caller list, either it raises or the claim was already a subset of
  what was observed. Widening *what may be observed* did not widen what may be asserted.

The clause is **narrower** than a caller-chosen label, which is the part of A2 that is a
tightening rather than an addition. `test_each_intake_admits_its_own_endpoint_and_no_other`
is the full 3×3 matrix, not the three diagonal cases: the six mismatches all raise and leave
`H` and `scan_scope` empty. Without that check a `threads.get` response could be recorded
through `record_list_page`, which would mint a `scan_scope` entry for a `messages.list` query
that never ran.

**Before / after** (`scratchpad/r4/a2_probe.py`, WS-08's first-choice pool source):

```
--- BEFORE (round-3 seal) ---
NO INTAKE: 'DispositionLedger' object has no attribute 'record_thread'
H = 0 []
DispositionInvariantError: shortlisted ids never entered H through an executed retrieval:
['thr-0', 'thr-1', 'thr-2'] …

--- AFTER (A2) ---
H = 6 ['H-thr']
SHORTLIST OK: size 3
```

`docs/ARCHITECTURE_DECISION.md` A.7a gains `(H-thr)` with a pointer to the amendment, so the
architecture and the code do not disagree about how many clauses there are. The amendment
record itself is unchanged — `ARCHITECTURE_AMENDMENTS.md` is where the reason lives.

**Deliberate limitation, stated here rather than found later:** a `threads.get` observation
appends **no `ScanScopeEntry`**. `scan_scope` is defined per executed *query*, and a
`threads.get` has none — giving it one would mean inventing a `q` and a `page_size` no call
carried. So a thread observation is visible in `ledger.origins` (with `endpoint` and
`thread_id`, both new fields on `HitOrigin`) and in the future trace, and **not** in the
response's `scan_scope`. If the eventual answer is that `threads.get` calls must be disclosed
in the response, that is a schema question for `scan_scope` or a sibling block, and it is not
one an implementer should settle inside a fix round.

### R-SEC-013 — the fold

`tools/guards/sweeps.py`, `_fold` / `_fold_call` / `_fold_step`.

All nine idioms are now **folded**, not documented: `bytes.fromhex().decode()`,
`"".join([...])`, `%`-formatting, `.format()`, `str.translate(str.maketrans(...))`, reversed
slicing, `int.to_bytes()`, and the two R-SEC identified as *accidental* catches —
`bytearray(...)` and `codecs.decode(...)` — which are now understood as calls rather than
picked up as loose literals by the fallback scan.

Three notes on how, because "we fold more" is the easy half:

* `%` and `.format()` are folded **by scanning, not by calling** `%`/`str.format`. Only `%s`
  and plain `{}`/`{0}` fields substitute; a conversion, a format spec, a keyword or an
  attribute lookup refuses the fold. A guard that reports text a call does not produce is
  worse than one that reports nothing, and `"{:>10000000}".format(x)` must not be able to
  make the sweep allocate.
* a codec that changes the text refuses the fold. `codecs.decode(x, "rot13")` is not
  transcoding, and reporting its input as though it were its output would be a lie in the
  guard's own voice.
* **`_fold` absorbs literals only on success.** This is a hole I found while fixing the
  rest, and it is the one I would put highest of the four: the round-3 fold wrote into
  `consumed` as it descended, so `"benchmarks/ground_truth/cases" + suffix` marked the
  literal absorbed, failed on `suffix`, returned `None` — and `_string_literals` then skipped
  the absorbed literal. **Neither the folded string nor the raw literal was ever reported.**
  Verified against the round-3 tree: 0 violations. Every new fold shape below it would have
  inherited the same hole.

What the fold does **not** read is now a list in the module docstring, and every entry on it
is asserted by `test_each_unfolded_idiom_is_named_in_the_docstring_rather_than_silently_missed`
— which fails both ways: if a listed shape starts being caught, the list is stale and the
test says so.

### R-SEC-014 — class-attribute dispatch

`class W: handler = os.write` then `W.handler(fd, body)` is caught. The class body's bindings
are kept as class attributes (not as module-scope names), and an `Attribute` call whose
receiver is a plain `Name` is resolved against them. Two tests: the write is caught, **and**
an unrelated local `handler` in another function is not — resolving the class attribute must
not put the name into module scope, which would have been R-SEC-015 again.

### R-SEC-015 — the false positive

This is the finding I treated as most serious, per the work order, and it drove the largest
rewrite: `_AliasIndex` (one flat table per module) is replaced by `_Scope`, a tree.

* bindings live in the scope that makes them, and lookup walks enclosing scopes **stopping at
  the first scope that binds the name at all** — including a binding this pass cannot read,
  which is exactly the case that produced the false positive. `_disk_writer = "{}={}".format`
  in `emit_metric` is unreadable, but it shadows, so `emit`'s `os.write` never reaches it;
* a class body is its own scope, and its names are not visible inside its methods (Python's
  rule), which is why `W.handler` needs the class-attribute path rather than the name path;
* within the scope that owns a name, the binding in force at a call is the **most recent one
  above it**. Across a scope boundary the last binding wins regardless of line, because a
  module-level name is fully bound by the time any function in that module runs.

Both of R-SEC's reproductions now report **exactly one** violation, at the real write's line —
the tests assert the line number, so "report nothing" cannot pass them by breaking the guard.

The line-ordering rule also closed a bypass R-SEC listed as an evasion rather than a finding:
`handler` assigned in both arms of an `if` and called after it is now reported, because the
binding nearest the call is the `os.write` one. And it removed a false positive nobody had
filed yet — `w = os.write; w(fd, b); w = str.upper; w(x)` reported both calls.

Probing the rewrite turned up three more shapes it initially got wrong, all now caught and
pinned (`test_a_binding_made_any_ordinary_way_still_resolves`): a walrus binding, a `global`
declaration routing an assignment to module scope, and — the one that bites — a method
calling `W.writer(...)` from *inside* `W`, which the first version resolved from outside the
class and reported nothing.

### R-SEC-016 — openers

The five-module allowlist is gone. The rule is now structural: **`.open()` on a receiver that
resolves to a module reads its mode at position 1**, the builtin's argument order. The only
mode-first `.open` in reach is `pathlib.Path.open`, which is a bound method on an instance and
therefore never resolves to a module — so position 0 remains the fallback for exactly the case
it was written for.

`wave.open(p, "wb")` is in the test set for one reason: `wave` appears on no list anywhere in
the file, so if the fix were still an allowlist that case would pass silently.

Two things are **not** structural, and are listed rather than dressed up:

* **constructors.** `zipfile.ZipFile`, `tarfile.TarFile`, `gzip.GzipFile`, `bz2.BZ2File`,
  `lzma.LZMAFile` and `io.FileIO` are named in `_MODE_AT_ONE_CONSTRUCTORS`. There is nothing in
  the *shape* of a name like `ZipFile` to recognise, so this is a list, it says so, and a
  writer-constructor that is not on it is missed. `sqlite3.connect("cache.db")` is the test
  case standing for that gap;
* **dbm flags.** `shelve` and the `dbm` family spell their mode as `r`/`w`/`c`/`n`, so they get
  their own character set, and `shelve.open(path)` — whose default flag creates the file — is
  reported with no flag argument at all.

Making `.open` structural has a cost, and paying it was part of the fix:
`webbrowser.open(url, 2)` puts an integer where a mode would be. An argument in the mode's
position that is a non-string constant is now **not a mode**, because reporting a browser
launch as a disk write is the R-SEC-015 failure mode with a different guard's name on it.
`wave.open(p)`, `tarfile.open(p, "r")`, `dbm.open(p)` and both `webbrowser` forms are asserted
clean.

---

## 4. What I did not fix, and why

* **R-RETR-003** (`FetchedIds._release` sets `_consumed` but never checks it, so one
  observation can be recorded twice and mint a second phantom `ScanScopeEntry`). MEDIUM, open,
  and **not in this work order** — the order lists six findings and says not to exceed it. It
  is a one-line change and I left it alone deliberately, not because I ran out of room. A2
  does not widen it: `record_thread` appends no scan-scope entry, and `_origins.setdefault`
  is idempotent, so re-recording a thread observation changes nothing observable.
* **Amendment A1.** Not built, per the work order. Nothing was weakened on the assumption it
  exists. One docstring changed: `FetchedIds` previously described WS-13 as cross-checking
  `http_requests`, which A1 says is necessary and not sufficient, and a residual paragraph
  that describes the wrong witness is how a later reviewer comes to believe the content half
  was closed by the count half. The text now says content witness and cites A1. **I did not
  touch `IMPLEMENTATION_PLAN.md`'s WS-13 acceptance line**, which is where R-RETR asked for
  the correction — that is a plan edit and it belongs to the orchestrator.
* **`EV-01`'s acceptance wording**: untouched, as instructed.
* **`RUBRIC_TRANSITIONS.md`**: untouched. No criterion marked PASS by me.
* **`FINDINGS_LEDGER.md`**: untouched. It has no rows for any of these findings and its header
  says an implementer may not maintain it.
* **Position *ranges*** are not validated (see §6).
* **Homoglyph detection, `getattr` chains, dict/decorator dispatch, instance attributes**:
  still not caught, still named in the guards' "Does not catch" lists, each now with a test
  asserting it really is missed so the list cannot drift in either direction.

---

## 5. Two signatures changed — Round-3 probes need one edit each

`FetchedIds(...)` now requires `endpoint`. A Round-3 probe that constructs one directly:

```python
FetchedIds(ids=[...], page_size=50)
# becomes
FetchedIds(ids=[...], endpoint=ObservedEndpoint.MESSAGES_LIST, page_size=50)
```

and a history observation must say so (`endpoint=ObservedEndpoint.HISTORY_LIST`, no page
size) or the intake will refuse it — that refusal is the A2 tightening working, not a
regression. `tests/fixtures/envelope_kit.py` grew `history_additions()` and
`observed_thread()` beside `fetched()`.

This was a real trade-off and I chose the explicit side: a default endpoint would have kept
every probe running unchanged, and it would also have meant an observation whose provenance
nobody stated is silently treated as a `messages.list` page. That is the shape of defect A2
exists to remove. The in-repo tests carry Round 2's and Round 3's attacks
(`test_a_hand_built_page_is_accepted_and_that_is_the_documented_residual`,
`test_no_shortlist_of_any_shape_can_grow_the_hit_set`, the `ast` single-writer test), so no
reproduction depends on a scratch file surviving a signature change.

---

## 6. Where this work is weakest

Ordered by how much I would expect a reviewer to get out of attacking it.

1. **The fold still does not follow a variable, and that defeats every content guard.**
   `PART = "ground"` then `PART + "_truth/cases.json"` is invisible — and so is any of the
   nine idioms with one operand behind a name. Nine idioms closed; the *general* case is
   wide open, which is the same "fixed the demonstrated shape, left the class" pattern R-SEC
   filed against Rounds 2 and 3. It is documented and tested as a gap rather than implied
   closed, but the honest summary of R-SEC-013 is **the enumerated idioms are caught and the
   category is not**. Closing it needs constant propagation through assignments, which is a
   different and much larger piece of work than folding one more call shape.
2. **Scope resolution approximates control flow with line numbers.** Within a scope the
   binding "in force" is the nearest one above the call. That is right for straight-line code
   and for the `if`/`else` case, and it is only an approximation for a `while` body that
   rebinds after the call, a `try`/`except` pair, or a call made before the binding it will
   actually see at runtime. It errs toward reporting in some of those and toward missing in
   others, and I have not characterised which. Comprehensions and lambdas are treated as part
   of the enclosing scope. `nonlocal` is not handled at all (`global` is).
3. **R-RETR-002 checks occupancy, not range.** Nothing verifies that a run's positions fall
   inside the thread: a map of a 10-message thread may still declare a run at positions
   900–904, and `stated_total` will not contradict it. I did not add the bound because the
   codebase does not settle whether `position` is 0- or 1-based — `envelope_kit` and the
   contract tests are 0-based, R-RETR's own reproduction is 1-based, and both build today.
   Deciding that convention changes what every existing fixture means, which is not an
   implementer's call inside a fix round. **It should be somebody's call next round**: an
   occupancy check over an unbounded position space is weaker than it looks.
4. **A2's endpoint is still caller-asserted.** `FetchedIds(ids=..., endpoint=...)` is an
   ordinary public constructor, so in-process code can mint a `threads.get` observation of
   ids nothing returned, exactly as it could mint a page in Round 3. A2 adds a clause; it does
   not add a witness, and A1 is still the only thing that would. The docstring says so.
5. **`record_thread` takes its `rung` from the caller** and nothing checks it, so a thread
   observed at L2 can be recorded as L5. The same is already true of `record_list_page`, so
   this is not new, but A2 doubled the number of places it is true.
6. **The constructor list in R-SEC-016** is a list, and lists go stale. It is named as one in
   the guard's own "Does not catch", with a test standing for what it misses, which is the
   most this layer can honestly offer.
