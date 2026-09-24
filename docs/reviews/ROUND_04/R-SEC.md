# R-SEC — Round 4 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance) · 2026-08-31. **Scope:** R-SEC-013..016 per
`ROUND_04/WORK_ORDER.md`. `HANDOFF.md` claims not trusted; every result below reproduced by
execution against the guard functions directly (`tools/guards/sweeps.py`), not by reading
the diff. Baseline reproduced clean: `pytest -q -m "not network"` 406 passed,
`python -m tools.guards` clean, `tests/test_guards.py` 50/50 passed. Probes live under
`/tmp/.../scratchpad/sec4/{r013,r013b,r014,r015,r016,r016b}/`; no project source or test
modified — each probe ran in an isolated temp dir through `GUARDS[name](Path(target))`.

## Verdicts

| Finding | Verdict | Basis |
|---|---|---|
| **R-SEC-013** | **CLOSED** as scoped | All nine idioms fold and are caught (verified individually against `ground-truth-isolation`); the half-completed-fold-absorbs-nothing hole is fixed (reintroduced shape now surfaces the raw literal instead of losing it). The general category — "the fold does not follow a variable" — is honestly disclosed as open, and I confirmed it: 8 boundary shapes bypass every content guard. Three of those (class attribute, dict/list element, function return) are not literally covered by the "variable" wording in the "Does not catch" list → **R-SEC-018** (documentation precision, LOW). |
| **R-SEC-014** | **CLOSED** as scoped | The exact claimed shape (`class W: handler = os.write` / `W.handler(...)`) is caught. Pushed further: instance attributes are un-caught and explicitly documented (OK). Nested-class attribute dispatch and dataclass field defaults are un-caught and **not** documented → **R-SEC-019**, **R-SEC-020** (MEDIUM each). |
| **R-SEC-015** | **CLOSED** | Both Round-3 false-positive reproductions now report exactly one violation, at the real write's line. A broad, realistic sweep reusing `copy`/`write`/`open`/`format`/`partial` across functions, a comprehension, a nested function, a class body/method and a parameter produced **zero** false positives. Pushing the line-number/control-flow approximation found one new false positive the specific documented examples don't name → **R-SEC-017** (MEDIUM). Two genuine false negatives were also found and are exactly the documented cases (while-loop, try/except) — acceptable. |
| **R-SEC-016** | **CLOSED** | Genuinely structural. `tarfile.open`, `shelve.open`, `zipfile.ZipFile`, `wave.open`, `gzip`/`bz2`/`lzma.open`, `dbm.open` (incl. the `dbm.gnu` submodule form) all caught correctly on clean filenames, with correct mode/flag reporting, and correct non-flagging of reads. Module aliases, `from`-import aliases, and `tarfile.TarFile.open` (classmethod-style) all resolve. `sqlite3.connect` is the one gap, and it's exactly the one HANDOFF names as a constructor with no shape to recognise. No new bypass found. |

---

## New findings

**R-SEC-017**
Severity: MEDIUM · Rubric: none — out-of-rubric (gate reliability), same class as R-SEC-015
Location: `tools/guards/sweeps.py::_Scope.function_named` (the `owner is not self` branch)
Reproduction: `sec4/scope_boundary/01_nested_call_before_rebind.py`: `process()` defines
`dispatch()` (calls `action(fd, body)`), sets `action = str.strip`, calls `dispatch()`, then
conditionally sets `action = os.write`. → **1 violation**, `action (bound to os.write)` at
`dispatch`'s call line — but at the moment `dispatch()` actually runs, `action` is
`str.strip`; the rebind is textually later and may never execute at all.
Expected: the comment justifying "last binding wins regardless of line" for a cross-scope
lookup reasons about **module-level** names ("fully bound by the time any function in that
module runs"). That does not hold for a closure referencing an **enclosing function's**
local, which can be invoked before a later rebind in the same call.
Actual: implemented generically for any scope crossing, not just module-level, so this
ordinary closure-then-reconfigure pattern is misclassified as an unconditional write. The
"Does not catch" list names two same-scope approximation failures (`while`, `try`/`except`)
but not this cross-scope one.
Required fix: restrict "last wins regardless of line" to the module scope specifically
(matching the comment's own justification), or name this shape in "Does not catch".

**R-SEC-018**
Severity: LOW · Rubric: SEC-01, SEC-03, SEC-08 (documentation precision, not a new bypass)
Location: `tools/guards/sweeps.py` module docstring, "What the fold does not read"
Reproduction: `sec4/r013b/b4_class_attribute.py`, `b5_dict_element.py`, `b5b_list_element.py`,
`b6_function_return.py` — each builds `"ground_truth/cases.json"` from a literal prefix
concatenated with a class attribute / dict item / list item / function return holding the
suffix. All four → **0 violations**.
Expected: the sole "does not read" bullet on this mechanism says "a value that travels
through a **variable**... because nothing here propagates assignments into expressions,"
with example `part = "ground"; part + "_truth/x"`.
Actual: an `ast.Attribute` receiver, an `ast.Subscript` on a non-string container, and a
`ast.Call` to a user function are three more shapes `_fold_step`/`_fold_call` don't
evaluate, for a reason distinct from "assignment propagation" — attribute lookup, container
indexing, and call-return substitution, not reassignment. None is literally "a value that
travels through a variable," even though all share the fold's real root cause and the
category is flagged elsewhere as "the biggest gap by far." Confirmed the bare-name cases
(`b1`,`b2`,`b3`) do match the given example — this is under-enumeration, not a hidden gap.
Required fix: broaden the bullet to name attribute/subscript/call-return indirection
explicitly, or fold them into the fold (each is small and bounded, unlike full constant
propagation).

**R-SEC-019**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_writes_to_disk`, `_qualified_target`
Reproduction: `sec4/r014/02_nested_class.py` — `class Outer: class Inner: handler =
os.write`, called from outside as `Outer.Inner.handler(fd, body)`. → **0 violations**.
`Inner`'s attribute table is built correctly (`handler` resolves to `("os","write")`
internally) but is registered on `Outer`'s own body scope, reachable only from a call
written directly inside `Outer`'s body. `_writes_to_disk`'s class-attribute path requires
the receiver to be a **bare** `ast.Name`; `Outer.Inner` is an `ast.Attribute`, so the branch
is skipped for any chained access — which is how a nested class is normally referenced.
Expected: R-SEC-014's own comment says a resolved, indexed receiver is honoured; a nested
class's attribute is indexed exactly as a top-level class's is.
Actual: distinct from every case in "Does not catch" — neither the instance-attribute case
nor a data-structure/decorator/getattr case.
Required fix: extend `_qualified_target`'s `ast.Attribute` branch to resolve a chained
receiver against nested `.classes` tables, or name this shape in "Does not catch".

**R-SEC-020**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_populate` (third pass, `ast.Assign`-only)
Reproduction: `sec4/r014/04_dataclass_field.py`, `04b_dataclass_field_default.py` — `@dataclass
class Writer: handler: Callable = field(default=os.write)` (and the bare-default form),
called as `Writer().handler(fd, body)`. → **0 violations**, both forms. A dataclass field is
an `ast.AnnAssign`, not an `ast.Assign`. `_statement_bindings` records the name as *bound*
(a placeholder with `target=None`) for `AnnAssign` too, but `_populate`'s third pass — the
one that calls `_record_assignment` to actually resolve a target — filters to
`isinstance(statement, ast.Assign)` only, so an `AnnAssign` target is never resolved even
when its value is `os.write` directly.
Expected: the class-attribute mechanism R-SEC-014 built is receiver-shape-agnostic; an
annotated class attribute is an ordinary way to declare one.
Actual: silently returns "bound but unresolvable," identical to what a genuinely unreadable
value produces — invisible in a way indistinguishable from a false clearance.
Required fix: extend the third pass to handle single-target `ast.AnnAssign` too, or name
"a dataclass field / annotated class attribute" in "Does not catch."

**Not filed:** a metaclass injecting `handler = os.write` via `ns["handler"] = os.write` in
`__new__` (`sec4/r014/03_metaclass.py`) also produced 0 violations, but the class body here
is genuinely empty — no AST node anywhere names the attribute, so no `ast`-based pass can
see it. Same category as the `eval`/`exec`/`getattr`-chain disclaimer already in the module
docstring; doesn't need its own bullet.

---

## Execution record

### R-SEC-013 — all nine idioms, individually, against `ground-truth-isolation`
| Idiom | Result |
|---|---|
| `bytes.fromhex(...).decode()` | Caught |
| `"".join([...])` | Caught |
| `"%s..." % "ground"` | Caught |
| `"{}...".format("ground")` | Caught |
| `str.translate(str.maketrans(...))` | Caught |
| `"..."[::-1]` (reversed slice) | Caught |
| `(N).to_bytes(23,"big").decode()` | Caught |
| `bytearray(b"...").decode()` | Caught (now genuinely, not by accident) |
| `codecs.decode(b"...", "utf-8")` | Caught (now genuinely, not by accident) |
| Half-completed fold: `"benchmarks/ground_truth/cases" + suffix` (unresolvable `suffix`) | Raw literal now reported — the round-3 absorption hole is closed |

### R-SEC-013 — boundary: does the fold follow indirection?
| Shape | Caught? | Documented? |
|---|---|---|
| Obfuscated value assigned to a local, local used in the same expression later | No | Yes — literal match to the given example |
| String built across two statements (`s = "ground"; s = s + "_truth/x"`) | No | Yes — literal match |
| Module-level constant referenced by name | No | Yes — reasonably, "variable" covers module scope |
| Class attribute (`Config.SUFFIX`) | No | **No** → R-SEC-018 |
| Dict element (`_PARTS["suffix"]`) | No | **No** → R-SEC-018 |
| List element (`_PARTS[0]`) | No | **No** → R-SEC-018 |
| Function return value (`suffix()`) | No | **No** → R-SEC-018 |
| f-string over a variable (`f"{part}_truth/x"`) | No | Ambiguous — subsumed by "variable" logically, but the docstring's separate positive claim about f-string placeholder folding could mislead; not filed separately |

### R-SEC-014 — class-attribute dispatch, pushed
| Shape | Caught? | Documented? |
|---|---|---|
| `class W: handler = os.write` / `W.handler(...)` (HANDOFF's claim) | **Yes** | — |
| Instance attribute (`self.handler = os.write`) | No | Yes, explicitly |
| Nested class (`Outer.Inner.handler = os.write` / `Outer.Inner.handler(...)`) | No | **No** → R-SEC-019 |
| Metaclass namespace injection | No | Not named, but subsumed by the general dynamic-construction disclaimer |
| Dataclass field, `field(default=os.write)` | No | **No** → R-SEC-020 |
| Dataclass field, bare default `handler: Callable = os.write` | No | **No** → R-SEC-020 |

### R-SEC-015 — false positives: reproductions, broad sweep, and the line-number boundary
| Probe | Result |
|---|---|
| Round-3 repro 1 (`_disk_writer` real write vs. unrelated `.format` in another function) | **Exactly 1** violation, correct line |
| Round-3 repro 2 (`do_copy` = `shutil.copy` vs. `list.copy` in another function) | **Exactly 1** violation, correct line |
| Broad ordinary-code sweep: `copy`/`write`/`open`/`format`/`partial` reused across 10 functions, a comprehension, a nested function, a class body+method, and a parameter, with exactly 2 real writes (`os.write`, `shutil.copy`) | **Exactly 2** violations, exact correct lines, zero false positives |
| Cross-scope: closure called before a later rebind of its free variable | **False positive** → R-SEC-017 |
| Same-scope `while` loop, rebind after the call | 0 violations — **false negative**, but exactly the documented "while body" case |
| Same-scope `try`/`except`, real write only in `except` | 1 violation (conservative; a genuine write path exists) |
| Same-scope `try`/`except`, real write only in `try`, gated by a runtime condition | 0 violations — **false negative**, exactly the documented "try/except pair" case |

### R-SEC-016 — openers, structural
| Module / shape | Result |
|---|---|
| `tarfile.open("dump.tgz","w")` (clean filename) | Caught, `mode='w'` |
| `shelve.open("records.db")` (default flag) | Caught, `flag=<default, creates>` |
| `zipfile.ZipFile("bundle.zip","w")` | Caught, `mode='w'` |
| `wave.open("sound.wav","wb")` | Caught, `mode='wb'` (wave is on no list at all) |
| `gzip`/`bz2`/`lzma.open(...,"wb")` | All caught |
| `dbm.open("cache.db","c")`, `dbm.gnu.open(...,"c")` | Caught, `flag='c'` |
| `sqlite3.connect("cache.db")` | 0 — the one documented, honest gap |
| `wave.open(p)`, `tarfile.open(p,"r")`, `dbm.open(p)` (reads) | All clean, no false positives |
| `webbrowser.open(url, 2)`, `webbrowser.open(url, new=2)` | Both clean, int arg not mistaken for a mode |
| `from shelve import open as sopen; sopen(...)` | Caught |
| Module alias (`import tarfile as tf; tf.open(...)`) | Caught |
| `tarfile.TarFile.open("dump.tar","w")` (classmethod-style) | Caught |
| `codecs.open(...,"w")` | Still caught, no regression |
| `io.open_code("script.py")` | Clean — unrelated read-only function, correctly not flagged |

---

## Per-criterion recommendations

| Criterion | Recommendation | Basis |
|---|---|---|
| SEC-01, SEC-03, SEC-08 | **Ready for PASS** on the fold as scoped (nine idioms + the absorption hole); the general variable/indirection gap remains explicitly open by design, matching the round's own honest framing. R-SEC-018 is a documentation refinement, not a blocker. | Full execution record above |
| SEC-05 | **Ready for PASS** on class-attribute dispatch and opener structurality as scoped; R-SEC-019/020 are new, real, undocumented MEDIUM gaps adjacent to the closed finding and should be scheduled, not treated as blocking this round's claim. | R-SEC-014, R-SEC-016 sections above |
| Gate reliability (out-of-rubric) | R-SEC-015's rewrite is a genuine, large improvement — a realistic, non-adversarial sweep produced zero false positives. R-SEC-017 is real but narrower and more contrived than the round-3 false positives it replaces; recommend fixing the module-scope-only justification mismatch before the next round rather than accepting it as documented, since a closure-based rebind is not an exotic pattern. | R-SEC-015 section above |

**Overall for the round:** all four Round-3 HIGH/MEDIUM findings close as scoped, verified
by execution rather than by trusting HANDOFF. Every fix that "fixes the demonstrated case,
leaves the general one" is honestly framed that way in its own docstring, which is the
standard `AGENT_LOOP.md` requires — with one exception (R-SEC-017's false positive isn't
enumerated by name, only by a general disclaimer) and one under-enumeration (R-SEC-018).
Two new MEDIUM bypasses (R-SEC-019, R-SEC-020) were found by pushing past the claimed shape,
consistent with the pattern this reviewer chain has found every round so far.
