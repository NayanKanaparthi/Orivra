# R-SEC — Round 6 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance) · 2026-08-31. Scope: R-SEC-021..025, the shape-bound
sweep (R-ARCH-016), per `ROUND_06/WORK_ORDER.md`. `HANDOFF.md` claims not trusted; every
result reproduced by execution. Environment rebuilt clean per the setup warning (`rm -rf
.venv .mypy_cache .pytest_cache .ruff_cache .hypothesis && uv sync --all-packages --extra
dev`) directly in `/root/mailweave` — no `/tmp` copy used, so the stale-install trap does
not apply here. Baseline reproduced: `pytest -q -m "not network"` **656 passed**, `mypy`
clean (62 files), `ruff check`/`format --check` clean, `python -m tools.guards` **7 guards
clean** over `server/src`, `rubric_status.py --check` unchanged (8 PASS / 105 NOT TESTED).
Probes under `/tmp/.../scratchpad/{guard_probes,guard_probes2,fp_sweep,fp_sweep2,fp_sweep3}`
and standalone scripts in the same scratchpad; no project source or test modified.

## Verdicts

**R-SEC-021 / R-ARCH-016 (shape-bound payload walk) — CLOSED, matrix confirmed and
extended.** Built a 2,000-level payload tree in eight spellings — plain `dict`,
`MappingProxyType`, `OrderedDict`, `defaultdict`, a hand-rolled `Mapping` ABC subclass,
a `dataclass`, an unrelated pydantic model, and a `__getitem__`-only object with no
`Mapping` registration and no `.parts` attribute — through all three entry points
(`parse_payload`, `model_validate`, keyword ctor). **All refuse correctly** except the
last. That one measures `(1, 1)` (silent undercount, `_child_parts`'s `getattr` fallback
finds no `.parts`) — but a control at small depth shows pydantic **itself** rejects this
object with `ValidationError: model_type` regardless of size, so there is no way to
actually build an oversized tree through it; the undercount is real but unreachable. Also
confirmed the real R-ARCH-016 vector (nested literal `Part` model instances, bottom-up)
refuses at all three entry points at depth 2,000 and builds at depth 3. No fourth
undercounting spelling found that pydantic would also accept.

**Sweep audit.** `wire.py::Affordance.mentions` — confirmed clear: nested `MappingProxyType`
and `tuple` values are rejected outright by pydantic's `JsonValue` (`"input was not a valid
JSON value"`); `MappingProxyType` passed as the whole `args` dict is coerced to a real
`dict`; `OrderedDict` passes through as `dict`. `mentions()` only ever walks
already-normalized output — claim holds. `config.py::load_config` — confirmed clear: `raw`
is always `json.loads` output, which the stdlib guarantees is
`dict`/`list`/`str`/`int`/`float`/`bool`/`None`; `isinstance(raw, dict)` is exhaustive for
that domain. `tools/guards/sweeps.py::_populate` — confirmed as a real third instance (see
R-SEC-023 below); same "one spelling, silently absent for the rest" shape. **No fourth
instance found**: grepped every `isinstance(x, dict/Mapping/list)` gate in `server/src`,
`tools/`, `harness/src` — only the four sites HANDOFF names remain. `content/mime.py`/
`envelope/measure.py` confirmed to walk only already-built models; `content/headers.py`/
`content/html_text.py`'s `isinstance(x, str)` gates confirmed exhaustive against their
library contracts (decode_header, lxml tag convention).

**R-SEC-022 (httpx submodule) — CLOSED for the named bypass, adjacent routes mostly (not
entirely) as documented.** `import httpx._client as hc; hc.Client()` now caught; confirmed
`hc.Client is httpx.Client` at runtime (`True`). Tried further: `getattr(httpx, "Client")` —
not caught, **documented**. `httpx.__dict__["Client"]` — not caught, fits the documented
"data structure" category. `type(existing_client)()` — not caught, **not documented** in
either gap list (narrow — recovering a class via `type()` of an instance obtained
elsewhere). `copy.deepcopy(a_client)` — correctly not flagged (not a constructor call).
Same-file subclass by its own name — not caught, matches the documented "subclass" gap
(docstring says "defined elsewhere"; the mechanism misses it regardless of file, so the
wording is narrower than the actual gap but the direction is right). **Re-export through a
differently-named module** (`from httpx_reexport import Client as X; X()`) — not caught:
resolves to `(module="httpx_reexport", attribute="Client")` and `_is_http_client_constructor`
only matches modules literally named `httpx`/`httpx.*`. Not documented anywhere. Narrow but
real, and it's the *same* "same object, different spelling" shape R-SEC-022 itself fixed —
noted, not filed as a new numbered finding given its narrowness, but worth a one-line
addition to the "Does not catch" list.

**R-SEC-023 (chained assignment) — CLOSED for the cited shape, matrix extended.**
Three-way chain (`a = b = c = os.write` / `httpx.Client`) resolves and is caught for both
guards. Walrus (`writer := os.write`) resolves and is caught (pre-existing machinery,
reconfirmed). **Starred unpacking** — not caught, **explicitly documented** in
`_assigned_pairs`'s own docstring as a deliberate non-goal. **`for` target**
(`for a in (os.write,): a(...)`, tuple form too) — not caught, for **both** guards. This is
technically inside the disk-write guard's "Does not catch" list ("a `for` target ... shadows
correctly, but...") but that sentence reads as a claim about *not misattributing*, not a
clear statement that a write reached through a `for` target is missed. Folded into
R-SEC-026 below rather than filed separately, since it shares that finding's root cause.
Augmented assignment: no realistic idiom rebinds a name to a callable via `+=`; tested and
irrelevant.

**R-SEC-024 (inheritance + gap-list honesty) — CLOSED, all six verified genuinely open and
genuinely documented.** Ran `tests/test_guards.py::test_each_documented_http_client_gap_is_really_a_gap`
(6 cases: instance attribute, instance held in a variable, dict element, factory return,
`getattr`, same-named subclass) — all pass. Independently reproduced three by hand with
fresh literals — same result. Inheritance fix verified: two-level class hierarchy, both
`Sub.handler(...)` and `Sub().handler(...)`, catches for both guards; an overriding
subclass correctly reports nothing.

**R-SEC-025 — the orchestrator's framing needs a correction, not the implementer's.** The
brief's line under R-SEC-024 ("claimed `field(default_factory=lambda: os.write)` now
handled") does **not** match what HANDOFF claims, and HANDOFF is the one that's right: built
`field(default_factory=os.write)` and `field(default_factory=lambda: os.write)` side by
side. The bare form **is** caught but crashes at construction — confirmed by executing it:
`TypeError: write expected 2 arguments, got 0` (`default_factory` is called with zero args).
The lambda form — the only one that works — is **not** caught, and HANDOFF says so plainly
("Documented, not fixed"), matching `ROUND_FIVE_WRITE_GAPS["lambda_default_factory"]`, which
pins exactly this. **Judgment: leaving it unfixed is acceptable.** LOW, out-of-rubric (per
Round 5's own filing), out of this round's work order, the documentation is now accurate,
and the guard is defense-in-depth around a stronger structural guarantee (SEC-05's real
acceptance test is a filesystem diff of an actual run), not the sole enforcement.

## New findings

**R-SEC-026**
Severity: MEDIUM · Rubric: SEC-05, SEC-07 (guard false-positive risk — same shared engine
R-SEC-021..024 touched)
Location: `tools/guards/sweeps.py::_own_statements`/`_populate` — comprehensions
(`ListComp`/`DictComp`/`SetComp`/`GeneratorExp`) and `Lambda` parameters are never visited
as bindings (only `ast.stmt` nodes are), so a name they bind is never added to
`_Scope.bound` and cannot shadow an outer resolved binding. `for`/`with`/`except` targets
*are* tracked (correctly shadow, just don't resolve — the ambiguous R-SEC-023 note above).
Reproduction: `import os` at module scope, then
`[os.replace("Windows","windows") for os in entries]` inside a function — `os` here is a
plain string loop variable, but the call is resolved through the *outer* `os` module import
and flagged as `os.replace` (a real entry in `_WRITE_QUALIFIED`). Confirmed for list comp,
dict comp, and a `lambda os: os.replace(...)` parameter (3 files, run against
`tools.guards.sweeps.unaudited_disk_write_sweep` directly): all three produce a violation
at the exact `.replace()` call line; a genuine unshadowed `os.replace(src, dst)` control in
the same file is also (correctly) caught, confirming this isn't a blanket suppression bug.
The same mechanism means the httpx guard is equally exposed to any name it resolves.
Expected: ordinary Python scoping (comprehensions and lambdas each introduce their own
scope) is respected, or the residue is named in both guards' "Does not catch" lists the way
`for`/`with` targets are gestured at.
Actual: a comprehension- or lambda-local name reusing an outer resolved binding's name
silently inherits that binding, producing a false positive on code that never touches the
resolved thing at all.
Required fix: track `ast.comprehension` targets and `Lambda` args as bindings in the
enclosing scope the same way function parameters are (`_walk_statements`' `FunctionDef`
branch already does the analogous thing), or explicitly document the gap in **both**
guards' docstrings (currently neither mentions it, and the http-client guard's own
`test_the_http_client_guard_names_what_it_resolves_and_what_it_does_not` does not check
for it either) and add it as a pinned false-positive-shaped test the way R-SEC-025 pins the
lambda-default_factory *false-negative*.

**R-SEC-027**
Severity: MEDIUM · Rubric: SEC-05
Location: `tools/guards/sweeps.py::_opens_for_writing` (pre-existing since R-SEC-010/016,
not touched this round, but newly surfaced by this sweep and not covered by either guard's
current "Does not catch" list)
Reproduction: a domain class unrelated to files with its own `.open(mode)` method
(`class Parser: def open(self, mode): ...`); `Parser().open("readonly")` is flagged as
`.open(mode='readonly')` — a **read-only** request reported as a write, because `"readonly"`
contains the letter `a` and the check is `_WRITE_MODE_CHARS & set(mode.value)`: *any*
character of `w`/`a`/`x`/`+` appearing *anywhere* in the string, not the string being an
actual mode token. `Parser().open("strict")` (no such characters) correctly passes,
confirming this is substring-driven, not `.open()`-driven.
Expected: the position-0 fallback (used whenever a receiver doesn't resolve to a real
module or class) only fires on values that are plausibly real open-mode strings.
Actual: any custom, non-file `.open(str)` API — sessions, connections, parsers, anything
using "open" as an ordinary English verb — misfires whenever its argument is an ordinary
English word containing one of four common letters, which is most of them ("active",
"auto", "manual", "exclusive", "readonly", ...).
Required fix: restrict the position-0 fallback to short strings that look like real mode
tokens (e.g. length ≤ 3, drawn from `{r,w,a,x,b,t,+}`), or narrow it to receivers this pass
already knows are file-like, and document what's left as an explicit gap rather than
leaving the false-positive direction unstated.

**R-SEC-028** (LOW, informational)
Severity: LOW · Rubric: none — out-of-rubric, guard usability
Location: `tools/guards/sweeps.py::ground_truth_sweep` (pre-existing, not touched this
round)
Reproduction: identifiers `is_manifestly_invalid` and `harness_the_energy` — ordinary
English words containing `manifest`/`harness` as substrings — both flagged as naming
ground-truth material.
Expected / Actual: substring match on `_GROUND_TRUTH_IDENTIFIER_TOKENS` fires on any
identifier containing the token, not just ones that reference the harness or a manifest.
Required fix: word-boundary match, or accept as a known, low-likelihood-collision cost
(none of these four tokens collide with any identifier currently in `server/src`).

## False-positive sweep (fresh, distinct from Round 5's and the implementer's)

Constructed independently: parameter/local shadowing of `os` (0 false positives — correctly
handled), comprehension/lambda shadowing of `os` (**3 false positives**, R-SEC-026),
`with`/`except ... as os:` shadowing (0 false positives — correctly handled, confirms that
half of the R-SEC-023 doc note), a non-file `.open(mode)` domain class (**1 false positive**
at `"w"`, **1 more** at `"readonly"`, R-SEC-027), ground-truth substring collisions (**2
false positives**, R-SEC-028). All corpora and exact commands are the scratchpad files
listed above; `unaudited-disk-write`/`unwrapped-http-client`/`ground-truth-isolation` were
run directly via `python -m tools.guards <dir> --guard <name>`. The seven shipped guards
remain clean over the real `server/src` tree throughout — none of these fire on shipped
code today; they are latent risk for future ordinary refactors, which is exactly the
"guards get switched off" failure mode the work order is worried about.

## Criteria recommendations

No SEC criterion moves to PASS this round — correctly so per the work order ("do not mark
any rubric criterion PASS"), and independently: the guards verified here are structural
scaffolding toward SEC-02/05/07, not their acceptance evidence, which requires a live
filesystem diff (SEC-05) and a network capture with a cold start (SEC-07) that this round's
scope did not include.

- **SEC-04 (Token storage hygiene, PASS)** — unaffected by this round's diff; no regression
  found (nothing touched `auth/tokenstore.py`, and it remains the sole
  `unaudited-disk-write` allowlist entry).
- **SEC-05 (no mail content at rest)** — remains NOT TESTED. This round strengthens the
  structural stand-in (`unaudited-disk-write` now resolves chained/tuple assignment and
  inheritance) but two new false-positive vectors (R-SEC-026, R-SEC-027) exist in the same
  guard; fix or document before leaning on it further. Still needs: an actual filesystem
  diff of a full suite run.
  R-SEC-025 remains an open, LOW, out-of-rubric, honestly-documented residue.
- **SEC-07 (egress allowlist / no telemetry)** — remains NOT TESTED. `unwrapped-http-client`
  is stronger (submodule + chained assignment + inheritance resolve now) but still has
  undocumented narrow gaps (`type(instance)()`, re-export module) and inherits R-SEC-026's
  false-positive exposure. Still needs: network capture with a cold start inside the
  allowlisted container, per the rubric's own acceptance text.
- **SEC-01/02/03/06/08** — untouched by this round's diff; remain NOT TESTED.
