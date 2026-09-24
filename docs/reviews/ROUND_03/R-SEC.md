# R-SEC — Round 3 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance, did not write this code or any prior review) · 2026-08-31
**Scope:** R-SEC-008..012 per `ROUND_03/WORK_ORDER.md`. `HANDOFF.md` claims not trusted;
every number below reproduced by execution. Baseline: `make check` clean (ruff, format-check,
mypy --strict/61 files, pytest 341 passed, guards clean, rubric-status 113 NOT TESTED / 0
transitions — unchanged, no criterion promoted by the implementer). Probes live under
`/tmp/.../scratchpad/sec3/{r008,r009,r010,r011,r012}/`; no project source or test modified.

## Verdicts

| Finding | Verdict | Basis |
|---|---|---|
| **R-SEC-008** | **PARTIALLY CLOSED** | The exact claim reproduces: original probe 0→4/4, `.decode()`/`.encode()` folding works. Pushed further with 9 more constant-obfuscation idioms: 7 are new, undocumented bypasses; 2 (`bytearray(...).decode()`, `codecs.decode(b"...")`) are "caught" only by accident (the raw `bytes` `Constant` survives unconsumed and is picked up by the unrelated fallback scan, not because the fold logic understands the call shape). |
| **R-SEC-009** | **PARTIALLY CLOSED** | All 4 originally-demonstrated shapes (`from os import write as w`, `from shutil import copy`, `_writer = os.write`, `functools.partial(os.write)`) plus the previously-documented `import os as o` case are caught exactly as HANDOFF states. Attacking the alias index itself: one genuinely new undocumented bypass (class-attribute dispatch), two evasions that fall under the existing broad "Does not catch" language, and **confirmed, concrete false positives** from the admitted scope-blindness. |
| **R-SEC-010** | **PARTIALLY CLOSED** | `io.open(p, "w")` now caught at position 1 as claimed; `io.open(p)` / `io.open(p, "r")` no longer falsely flagged as "computed at runtime", confirmed both ways. `codecs`/`gzip`/`bz2`/`lzma` all correctly resolve to position 1. But the fix is a 5-module allowlist, not a structural fix: any *other* resolved stdlib opener with the same `(path, mode)` shape reproduces the identical original bug (position-0 fallback reading the path, not the mode) — demonstrated with `tarfile.open` and `shelve.open`. `zipfile.ZipFile`, a different-shaped stdlib writer, is missed entirely and isn't covered by the "third-party library" disclaimer (zipfile is stdlib). |
| **R-SEC-011** | **CLOSED** | Every claim verified by execution: RLO stripped and declared from Subject, From display name, and attachment filename (keyed by header name / part_id, never the filename text — confirmed the reduction record itself never contains the stripped string); Hebrew and Arabic in both subject and filename survive byte-for-byte; zero-width characters (ZWSP/ZWNJ/ZWJ) stripped from both surfaces. Homoglyphs (Cyrillic `а` for Latin `a`) pass through completely untouched — not a contradicted claim, since nothing anywhere claims homoglyph detection. |
| **R-SEC-012** | **CLOSED** | Reproduced independently with a real subprocess (not a synthesized file): a live process's own in-flight temp file survives a concurrent sweep (`swept=0`); the identical file is swept once the process actually exits (`swept=1`); the real `credentials.json` path itself is never touched; a same-prefix file with the wrong field-count naming convention is left alone; a temp-shaped name carrying *this reviewer's own* live PID survives; a temp-shaped name with a pid far outside any plausible live range is swept. PID reuse cannot cause a live writer's file to be deleted — `os.kill(pid, 0)` checks the PID *currently* in use, so a temp file whose recorded PID is presently alive is always protected, whichever process owns that PID number; the only failure mode reuse can cause is under-sweeping (documented, and safe). |

---

## New findings

**R-SEC-013**
Severity: HIGH · Rubric: SEC-01, SEC-03, SEC-05, SEC-08
Location: `tools/guards/sweeps.py::_fold`, `_string_literals`
Reproduction: `/tmp/.../sec3/r008/{02,04,05,06,07,08,09}_*.py`, each isolated, each producing
the literal text `ground_truth/cases.json` at runtime with no `str`/`bytes` `Constant`
containing that substring anywhere in the source: `bytes.fromhex("6772...6f6e").decode()`;
`"".join(["ground_tr","uth/cases.json"])`; `"%s_truth/cases.json" % "ground"`;
`"{}_truth/cases.json".format("ground")`; `"groundZtruth/cases.json".translate(str.maketrans("Z","_"))`;
`"nosj.sesac/hturt_dnuorg"[::-1]`; `(9908255...).to_bytes(23,"big").decode()`. All seven →
**0 violations**. (`bytearray(b"...").decode()` and `codecs.decode(b"...", "utf-8")`
register 1 violation each, but only because the inner `bytes` `Constant` is never marked
`consumed` — `_fold` returns `None` for both shapes without visiting the literal, so the
unrelated plain-`Constant` fallback catches it as a loose literal by accident, not because
these calls are understood as transcoding.)
Expected: R-SEC-008's stated intent — "the forbidden thing is the *text*, not the
spelling" — extends to any statically-knowable text, which all seven of these are.
Actual: `_fold` recognises exactly `Constant`, `BinOp(Add)`, `JoinedStr`, and `.decode()`/
`.encode()` on a receiver it can already fold. Every other stdlib string-construction idiom
is invisible, and none is named in any guard's "Does not catch" list.
Required fix: extend the fold (`str.join` over foldable elements, `%`/`.format()` with
foldable operands, `bytes.fromhex`, `int.to_bytes`, foldable `Subscript` slicing), or name
these idioms explicitly as gaps and stop relying on the `bytearray`/`codecs.decode` accident.

**R-SEC-014**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_writes_to_disk`
Reproduction: `/tmp/.../sec3/r009/11_evade_class_attribute.py`:
`class Writer: handler = os.write` then `Writer.handler(fd, body)` → **0 violations**. The
class-body assignment `handler = os.write` *is* indexed by `_build_alias_index` (a class
body is an ordinary `Assign`, indistinguishable from module scope to this pass) — but
`_writes_to_disk` only resolves an `Attribute` call's receiver through `_resolve_module`
(imported-module aliases), never through `index.functions` for a receiver that is a plain
`Name`. `ClassName.attr(…)` falls through every branch and is never classified.
Expected: the guard's own comment ("a *resolved* receiver is never re-read... at position
0 as a fallback") implies any indexed alias is honoured; this one is indexed and still missed.
Actual: distinct from the three documented gaps (`getattr`, "alias... inside a data
structure or returned from a function", "blind to scope and re-binding") — a class
attribute is none of those; it is a plain, named assignment the index already captured,
defeated purely by the call-classification code never looking there.
Required fix: resolve `<Name>.<attr>(...)` against `index.functions` when `<Name>` is not
a module, or add "a class attribute bound to a disk-write function" to "Does not catch".

**R-SEC-015**
Severity: MEDIUM · Rubric: none — out-of-rubric (gate reliability / maintainability)
Location: `tools/guards/sweeps.py::_build_alias_index`
Reproduction: `/tmp/.../sec3/r009/21_false_positive_two_functions.py` — two unrelated,
ordinary functions in one module. `emit`: `_disk_writer = os.write; _disk_writer(fd,
body)` (a real write, correctly caught). `emit_metric`, unrelated: `_disk_writer =
"{}={}".format; return _disk_writer(name, value)` (a string formatter, no I/O at all) →
**both** report as `_disk_writer (bound to os.write)` — 2 violations for 1 real write.
`emit_metric`'s call is a false positive purely because `emit` used the same local
variable name elsewhere in the file. Companion `20_false_positive_scope_blind.py`
reproduces the same effect with `do_copy = shutil.copy` vs. `do_copy = list.copy` — the
exact shape HANDOFF §4.2 names as a risk ("a local `copy = ...` makes later `copy(...)`
calls report").
Expected/Actual: HANDOFF already discloses this as the round's weakest point and accepts it
as an intentional false-positive-favouring trade-off; this finding does not contradict that
disclosure, it demonstrates the risk is not theoretical — it fires on two independent,
non-adversarial functions that merely reuse a local variable name, a pattern plausible in
real refactors. Filed because "self-acknowledged" and "concretely reproduced" are different
states of evidence.
Required fix (optional per HANDOFF's framing, recommended before this guard runs
unattended): scope the index per-function rather than module-flat, or record the
trade-off in the criterion write-up so a future disable-the-gate decision has this evidence.

**R-SEC-016**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_is_write_shape`, `_PATH_FIRST_OPEN_MODULES`
Reproduction: `05_tarfile_open_write.py` — `tarfile.open("leak.tar", "w")` → caught, but
only because `"leak.tar"` contains `a` (the position-0 fallback inspecting the *path*, the
exact pre-fix bug). Same call, ordinary filename, `08_..._clean_filename.py` —
`tarfile.open("dump.tgz", "w")` → **0 violations**. Identical pattern for
`shelve.open("records.db")` (default `flag="c"`, a write) in `09_..._clean_filename.py` →
**0 violations**. Separately, `07_zipfile_write.py` — `zipfile.ZipFile("leak.zip", "w")`, a
constructor call rather than `.open()` — → **0 violations**, not even by accident.
Expected: the code comment on `_is_write_shape` claims "a resolved receiver is never
re-read under pathlib's signature as a fallback."
Actual: false whenever the resolved module is not one of the five names in
`_PATH_FIRST_OPEN_MODULES`. `tarfile`/`shelve` *do* resolve (`_resolve_module` returns
`"tarfile"`/`"shelve"`, not `None`) and are re-read at position 0 anyway — reproducing
R-SEC-010's original defect for every other stdlib opener sharing the builtin's argument
order. `zipfile`'s constructor-shaped writer is a different gap: not `.attr == "open"` at
all, and it is stdlib, not the "third-party library's own file API" the docstring accepts.
Required fix: default position-1 for *any* receiver that resolves to a real module (fall
back to position-0 only when unresolved, `pathlib.Path`'s actual case), and add
`zipfile.ZipFile`/`tarfile.TarFile` to `_WRITE_QUALIFIED` or name them as an explicit gap.

---

## Execution record

### R-SEC-008 — byte/string-literal folding
| Probe | Result |
|---|---|
| Original 4-marker probe (`b"...".decode()` × 4), verbatim | **4/4 caught**, matches HANDOFF |
| `bytearray(b"...").decode()` | Caught — **by accident** (unconsumed raw `Constant` in the fallback scan, not `.decode()` folding: `_fold` on the outer call recurses into a `Call(Name('bytearray'), ...)`, which no branch handles, so it returns `None` without marking the inner literal `consumed`) |
| `bytes.fromhex("67726f...").decode()` | **0 — new bypass**, undocumented |
| `codecs.decode(b"ground_truth/cases.json", "utf-8")` | Caught — same accident as `bytearray` (the `.attr == "decode"` check matches on attribute name alone, matches `codecs.decode`'s own name coincidentally, then fails to fold `codecs`) |
| `"".join(["ground_tr", "uth/cases.json"])` | **0 — new bypass**, undocumented |
| `"%s_truth/cases.json" % "ground"` | **0 — new bypass**, undocumented (`%` is `ast.Mod`, `_fold`'s `BinOp` branch only handles `ast.Add`) |
| `"{}_truth/cases.json".format("ground")` | **0 — new bypass**, undocumented |
| `"groundZtruth/cases.json".translate(str.maketrans("Z","_"))` | **0 — new bypass**, undocumented |
| `"nosj.sesac/hturt_dnuorg"[::-1]` (reversed literal) | **0 — new bypass**, undocumented (`Subscript` unhandled) |
| `(9908255...).to_bytes(23, "big").decode()` | **0 — new bypass**, undocumented |

### R-SEC-009 — alias index: verify, evade, false-positive
| Probe | Result |
|---|---|
| `from os import write as w` / `from shutil import copy`, bare call | Caught, matches HANDOFF |
| `_writer = os.write; _writer(fd, body)` | Caught, matches HANDOFF |
| `functools.partial(os.write)` then call | Caught (both the `partial(...)` site and the call site), matches HANDOFF |
| `import os as o; o.write(...)` | Caught, matches HANDOFF |
| Conditional masking: `handler = json.dumps` in one branch, `handler = os.write` in the other, single call after the `if` | **0 — evasion**, but plausibly within "blind to... re-binding" |
| Class attribute: `class Writer: handler = os.write` then `Writer.handler(fd, body)` | **0 — new bypass** (R-SEC-014), not covered by any documented phrase |
| Dict dispatch: `{"w": os.write}["w"](fd, body)` | **0 — evasion**, plausibly within "alias... inside a data structure" |
| Decorator substitution: `@substitute(os.write)` replacing a decoy function, then calling the decorated name | **0 — evasion**, plausibly within "returned from a function" |
| False positive: two functions, one real `_disk_writer = os.write`, another unrelated `_disk_writer = "{}={}".format` | **2 violations reported for 1 real write** — confirmed false positive (R-SEC-015) |
| False positive: `do_copy = shutil.copy` (real) vs. `do_copy = list.copy` (unrelated) in a second function | Same pattern, confirmed |

### R-SEC-010 — receiver-then-mode-position
| Probe | Result |
|---|---|
| `io.open("output.log", "w")` | Caught at position 1, matches HANDOFF |
| `io.open(p)` / `io.open(p, "r")` (reads) | Clean, no false "computed at runtime" — matches HANDOFF |
| `codecs.open(...)`, `gzip.open(...)`, `bz2.open(...)`, `lzma.open(...)`, each with a write mode | All caught at position 1 |
| `tarfile.open("leak.tar", "w")` | Caught — by the position-0 accident (`a` in `leak.tar`) |
| `tarfile.open("dump.tgz", "w")` (clean filename) | **0 — new bypass** (R-SEC-016) |
| `shelve.open("records.db")` (default write flag, clean filename) | **0 — new bypass** (R-SEC-016) |
| `zipfile.ZipFile("leak.zip", "w")` | **0 — new bypass** (R-SEC-016), missed entirely, no accident either way |

### R-SEC-011 — bidi/zero-width on headers and filenames
| Probe | Result |
|---|---|
| RLO spoof in `Subject` | Stripped, declared `hidden_content`/`BIDI_OVERRIDE`, `header=subject`, readable text (`Invoice_...`) intact |
| RLO spoof in `From` display name | Stripped, declared, `header=from` — confirms coverage beyond `Subject` |
| RLO spoof in attachment filename | Stripped, declared keyed by `part_id` (`0.1`) — reduction record does not itself carry the filename text |
| Hebrew subject + filename (`שלום עולם`) | Byte-for-byte preserved in both |
| Arabic subject + filename (`مرحبا بالعالم`) | Byte-for-byte preserved in both |
| Zero-width (ZWSP/ZWNJ/ZWJ) in subject | Stripped, declared `ZERO_WIDTH` |
| Zero-width in filename | Stripped, declared `ZERO_WIDTH`, keyed by `part_id` |
| Homoglyph (Cyrillic `а` for Latin `a`) in subject | Passes through unchanged — no guard anywhere claims this, not a contradiction |

### R-SEC-012 — orphan sweep vs. live/dead/reused PIDs
| Probe | Result |
|---|---|
| Real subprocess holding its own temp file, swept while still alive | `swept=0`, file survives |
| Same file, same call, after the subprocess actually exits | `swept=1`, file removed |
| Real `credentials.json` path, sweep run against it | Untouched |
| Decoy `.credentials.json.bak` (wrong field count) | Untouched |
| Temp-shaped file naming *this reviewer process's own* live PID | Untouched |
| Temp-shaped file naming an implausible/far-out PID (999999) | Swept |
| PID-reuse direction check | A live PID can only ever *protect* a name from sweeping (an under-sweep, already documented), never cause deletion of a name whose PID is genuinely alive — `os.kill(pid,0)` is checked against whatever process currently holds that number |

---

## Per-criterion recommendations

| Criterion | Recommendation | Basis |
|---|---|---|
| SEC-01, SEC-03, SEC-08 | **NOT YET PASS** | R-SEC-013: seven more constant-folding idioms defeat all four content-matching guards, undocumented; two more "pass" only by an accident of the fallback scan. |
| SEC-05 | **NOT YET PASS** | R-SEC-014/015/016 leave `unaudited_disk_write_sweep` with one undocumented bypass shape, confirmed false positives from its own admitted trade-off, and a mode-position fix that is a 5-module allowlist rather than a structural correction. |
| SEC-04 | Unchanged from Round 2 — **PASS-ready on atomicity**; R-SEC-012's housekeeping gap is now closed and independently reverified. |
| INJ-04 | **Ready for PASS** on the bidi/zero-width scope specifically | R-SEC-011 verified in full: body, Subject, every header's display value, and attachment filenames are all covered, Hebrew/Arabic undamaged, reduction records don't leak the stripped text. Homoglyph spoofing remains open but was never claimed, so it does not block this criterion — track separately if in scope. |
| SEC-07 | Unchanged from Round 1/2 (R-SEC-004) — still open, out of this round's work order. |

**Overall for the round:** none of R-SEC-008/009/010 can move to PASS as stated. Each fix
genuinely closes the exact shapes it names — verified by execution, not by trusting
HANDOFF — but each leaves a same-shaped, same-severity class of gap open and undocumented,
which is the same pattern R-SEC found in Round 2 (fix the demonstrated case, leave the
general one). R-SEC-011 and R-SEC-012 are the two findings that are actually closed: broad,
executable claims, verified from multiple independent angles, nothing found to contradict
them.
