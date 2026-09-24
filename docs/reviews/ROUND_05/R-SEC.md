# R-SEC — Round 5 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance) · 2026-08-31. **Scope:** R-SEC-004/006/007 (never
re-verified since Round 1), R-SEC-017/018/019/020 (Round 4 mediums), the new seventh guard,
per `ROUND_05/WORK_ORDER.md`. `HANDOFF.md` claims not trusted; every result reproduced by
execution. Baseline reproduced clean: `pytest -q -m "not network"` 557 passed,
`python -m tools.guards` clean (7 guards). Probes under `/tmp/rsec5/`; no project source or
test modified.

## Part A verdicts

**R-SEC-004 — CLOSED for the direct-call path.** `check_url` now catches any `.scheme`/`.host`
parse failure and re-raises `EgressBlocked`; the three malformed-punycode reproductions all
raise the typed error, and a real allowlist decision still fires for a host that parses
(`test_the_unparseable_host_path_does_not_swallow_a_real_allowlist_decision`). **The
client-level residue is honestly documented, not dropped.** I attacked it directly: seven
malformed hosts fed through `httpx.Client(transport=AllowlistTransport(...)).get(...)`
(including two crafted beyond the original two) all raised `idna`'s own exception with **zero**
requests reaching the inner transport — confirmed by `inner.requests == []` in every case. No
host shape got past the lazy `idna` decode silently; there is no bypass here, only an untyped
but fail-closed error surface, exactly as the module docstring and tests state.

**R-SEC-006 — CLOSED for literal `dict` input, but the coverage claim overreaches.** The
`mode="before"` bound (`refuse_unbounded_payload`) correctly refuses a 6,401-part payload and
holds on both `parse_payload()` and `MessagePayload.model_validate()` directly, verified at the
exact boundary (part count == cap accepted, cap+1 refused). **Bypass found:** the validator
gates on `isinstance(data, dict)`; pydantic-core itself accepts any `Mapping`. A payload wrapped
in `types.MappingProxyType` (stdlib, not a contrived class) — 32,000 parts, 5× the cap — built
successfully in 0.15s through **both** `parse_payload()` and `model_validate()`, with the shape
bound never invoked. This contradicts the docstring's claim that "every construction path is
covered." See R-SEC-021.

**R-SEC-007 — CLOSED, verified.** `PAYLOAD_DEPTH_CAP=120` is genuinely below the real guard: I
independently measured pydantic's own recursion limit for `Part` at 255 (matches HANDOFF's
number). At the exact boundary, a payload at depth==cap is accepted; depth==cap+1 is refused
cleanly as `ContentProcessingError`, never `ValidationError` or `RecursionError` — the "fails
safely at the boundary" claim holds.

## Part B verdicts

**R-SEC-017 — CLOSED, precisely as scoped.** Three-way test: module-scope free variable keeps
"last wins" (still flagged even though the write-binding is textually after the call);
function-scope closure called before a later rebind is now correctly **not** flagged (the fix);
function-scope closure whose binding sits **above** its creation is still correctly flagged.
My own 167-line ordinary-code sweep (closures over loop variables, `functools.wraps`
decorators with a nested `retry` factory, generators, a `@contextmanager`, a `Formatter`
subclass hierarchy, comprehension name-shadowing, `except ValueError as last`, a bound-but-
uncalled `shutil.copy` decoy) produced **exactly one** violation, at the one real `os.write`.
Zero false positives on a corpus independent of the implementer's own.

**R-SEC-019 — CLOSED, pushed to three levels.** `A.B.C.handler(...)` (3-deep nesting, beyond
the implementer's own 2-and-3-level tests) resolves correctly; a non-write nested class
attribute produces no false positive.

**R-SEC-020 — CLOSED for `default=`; `default_factory=` claim is narrower than stated.** Bare
annotated default and `field(default=os.write)` both resolve correctly. HANDOFF states
`_field_default_target` "learns `field(default_factory=...)`" — true only for the syntax, not
for working code: `field(default_factory=os.write)` resolves and is flagged, but that form
**crashes at construction** (`dataclasses` calls the factory with zero args; `os.write()` raises
`TypeError`). The only functioning idiom, `field(default_factory=lambda: os.write)`, is
**not** resolved (`_qualified_target` doesn't evaluate `ast.Lambda`) and isn't named anywhere.
See R-SEC-025.

**R-SEC-018 — CLOSED.** The four-shape enumeration is in the docstring, and
`FOLD_INDIRECTION_SHAPES` executes all four (plus the original variable case) against the real
`ground-truth-isolation` guard, confirming each still bypasses the fold as described.

## The seventh guard: `unwrapped-http-client`

**Claim:** the only allowed `httpx.Client()`/`AsyncClient()` construction site in `server/**`
is `net/egress.py`; catches direct calls, module aliases, `from`-imports, and plain rebinding;
documented gaps are data-structure/factory/`getattr` values, third-party sockets, and a
same-named subclass.

**Verified as claimed:** 01–04 (direct, module alias, from-import alias, rebinding) all caught;
09–11 (class attribute, 2-level nested class attribute, dataclass field) also resolve, correctly
reusing R-SEC-019/020's mechanism though not mentioned in this guard's own docstring. 05–08
(`getattr`, factory return, dict lookup, same-named subclass) correctly not caught, matching the
documented gap list.

**New bypass found, not documented:** `import httpx._client as hc; hc.Client()` builds the
*exact same class object* as `httpx.Client` (`hc.Client is httpx.Client` → `True`) with the
real, unwrapped `httpx.HTTPTransport` — confirmed by constructing one and checking
`isinstance(c._transport, AllowlistTransport)` → `False`. The guard's module-string match is
exact (`"httpx"` only), so `httpx._client`, `httpx._transports.default`, or any other private
submodule path is invisible to it. This is an ordinary one-line import, not obfuscation. →
R-SEC-022.

**New undocumented residue:** `self.ctor = httpx.Client` (instance attribute) and
`w = Writer(); w.ctor()` (instance held in a variable) both bypass this guard — the disk-write
guard's own docstring names both gaps explicitly; this guard's "Does not catch" list, written
fresh this round, names neither. → folded into R-SEC-024.

## New findings

**R-SEC-021**
Severity: MEDIUM · Rubric: none — out-of-rubric robustness (R-SEC-006 residue)
Location: `content/payload.py::_shape_is_bounded_before_it_is_built`
Reproduction: `MessagePayload.model_validate(types.MappingProxyType(raw))` where `raw` has
32,000 parts — see above. `git diff`-free repro at `/tmp/rsec5/egress/mapping_bypass2.py`.
Expected: docstring: "every construction path is covered, including a direct
`MessagePayload.model_validate(...)`."
Actual: `isinstance(data, dict)` excludes any Mapping that is not a literal `dict`; pydantic
itself has no such restriction, so the shape bound and the model disagree on what counts as
valid input.
Required fix: use `isinstance(data, Mapping)` (`collections.abc`), or document the residue the
way R-SEC-004's client-level gap is documented.

**R-SEC-022**
Severity: MEDIUM · Rubric: SEC-07 (gate reliability, same class as R-ARCH-006)
Location: `tools/guards/sweeps.py::unwrapped_http_client_sweep`, `_HTTP_CLIENT_CONSTRUCTORS`
Reproduction: `/tmp/rsec5/httpguard/18_from_dotted_submodule.py` — `import httpx._client as hc;
c = hc.Client()`. 0 violations. Runtime-confirmed: same class, unwrapped transport.
Expected: "the only supported way to get an HTTP client" (egress.py docstring); guard exists to
enforce it structurally.
Actual: matches on the exact module string `"httpx"`; `httpx._client` (where `Client` is
actually defined) is a different string and unrecognised.
Required fix: resolve the *module attribute chain* to the real class object's home (or treat
any `httpx.*` submodule as `httpx` for this purpose), or name it in "Does not catch."

**R-SEC-023**
Severity: MEDIUM · Rubric: SEC-05, SEC-07 (shared resolution-engine gap)
Location: `tools/guards/sweeps.py::_populate` (third pass, `len(statement.targets) != 1`)
Reproduction: `a = b = os.write; b(3, b"x")` → 0 violations from `unaudited-disk-write`.
`a = b = httpx.Client; b()` → 0 violations from `unwrapped-http-client`. Both confirmed.
Expected: "a plain re-binding... is resolved" (disk-write docstring); chained assignment is a
plain rebinding, not an evasion.
Actual: the resolution pass explicitly skips every `ast.Assign` with more than one target, so
**neither** name resolves — both are recorded bound-but-unresolvable, indistinguishable from a
genuinely unreadable value. Affects every guard built on this engine.
Required fix: iterate `statement.targets` in the third pass instead of requiring exactly one.

**R-SEC-024**
Severity: LOW · Rubric: SEC-05, SEC-07 (documentation precision + narrow residue)
Location: same engine; `class_attribute`/`_owner`, and `unwrapped_http_client_sweep`'s docstring
Reproduction: `class Base: handler = os.write` / `class Sub(Base): pass` / `Sub().handler(...)`
(and `Sub.handler(...)`) — 0 violations; inheritance/MRO is never walked, only a class's own
body. Separately, `unwrapped_http_client_sweep`'s "Does not catch" list omits the instance-
attribute and instance-held-variable gaps that the disk-write guard (same mechanism) documents
for itself.
Expected: a guard's own docstring names the gaps its own mechanism has, per the round's
standing rule.
Actual: inherited class attributes are an ordinary, undocumented class-hierarchy gap; the new
guard's gap list is a strict subset of what its shared mechanism actually misses.
Required fix: name both in the respective docstrings, or (for inheritance) walk base classes
when resolving `class_attribute`.

**R-SEC-025**
Severity: LOW · Rubric: none — out-of-rubric (R-SEC-020 residue)
Location: `tools/guards/sweeps.py::_field_default_target`
Reproduction: `field(default_factory=lambda: os.write)` → 0 violations (not resolved).
`field(default_factory=os.write)` → 1 violation, but this form raises `TypeError` at
`Writer()` construction and never runs.
Expected: HANDOFF's "`_record_assignment` learns... `field(default_factory=...)`" to cover the
form that actually works.
Actual: `_qualified_target` doesn't evaluate `ast.Lambda`, so the only functioning
`default_factory` idiom for a callable-typed field is missed while a non-functioning one is
"caught."
Required fix: correct the HANDOFF claim's precision, or evaluate a single-expression lambda
body the same way an attribute value is evaluated.

## Execution record

| Probe | Guard/module | Result |
|---|---|---|
| 3 malformed-punycode hosts direct + through client (incl. 4 new variants) | egress | All raise typed/foreign error resp.; **0** ever reach inner transport |
| Depth boundary (cap, cap+1); real pydantic recursion limit, measured | payload.py | cap accepted, cap+1 refused cleanly; real limit=255, cap=120 (safe margin) |
| `MappingProxyType`-wrapped 32k-part payload | payload.py | **BYPASS** — R-SEC-021 |
| Module/function/module-crossing closure trio | disk-write | last-wins / not-flagged / flagged — all as R-SEC-017 claims |
| 3-level nested class attribute | disk-write | Caught |
| `field(default=...)`, bare annotated default | disk-write | Both caught |
| `field(default_factory=lambda: os.write)` vs `field(default_factory=os.write)` | disk-write | lambda form missed; broken form "caught" — R-SEC-025 |
| 167-line original ordinary-code sweep (closures/decorators/generators/context managers/hierarchy/comprehension shadowing/`except..as`) | disk-write | **0 false positives**, 1/1 real write found |
| 8 documented residues (`self.x`, instance-held var, dict, factory, `getattr`, `sqlite3.connect`, closure-after-rebind, decorator-install) | disk-write | All 8 confirmed genuinely uncaught, all genuinely documented |
| Chained assignment `a = b = X` | disk-write, http-client | **BYPASS on both** — R-SEC-023 |
| Base-class attribute via subclass (class + instance call) | disk-write | **BYPASS**, undocumented — R-SEC-024 |
| Direct/alias/from-import/rebind httpx.Client construction | http-client | All 4 caught |
| `getattr`/factory/dict/same-named-subclass httpx client | http-client | All 4 correctly uncaught, matches doc |
| `import httpx._client as hc; hc.Client()` | http-client | **BYPASS, functional and undocumented** — R-SEC-022 |
| `self.ctor=`/instance-held-var httpx client | http-client | Uncaught, undocumented in this guard — R-SEC-024 |
| Full suite + guards | — | 557/557 pass, 7/7 guards clean throughout |

## Per-criterion recommendations

| Criterion | Recommendation | Basis |
|---|---|---|
| SEC-07 (egress) | Ready for PASS on the two-host allowlist and R-SEC-004's fix; the client-level residue is real, fail-closed, and honestly documented — not a blocker. R-SEC-022 (new guard bypass) should be fixed before relying on `unwrapped-http-client` as SEC-07's structural enforcement. | R-SEC-004, R-SEC-022 |
| SEC-05 (no content at rest) | Not blocked by anything new; R-SEC-023/024 are guard-engine gaps affecting adoption enforcement generally, not evidence of an actual writer in the tree today. Schedule, don't block. | R-SEC-023, R-SEC-024 |
| INJ-04 | **Now genuinely ready for a full-scope PASS, not just bidi** — but only once the ledger row is rewritten to cite all three rounds together, which R-ARCH-009 required and which is still outstanding. Evidence: Round 1 covered visible-text extraction, hidden-content flagging, no-network (autouse socket block + XXE/billion-laughs proven not fetched), no entity resolution; R-SEC-002 (nesting DoS) closed and independently reverified in Rounds 2–3; R-SEC-005 (bidi) closed and verified in Round 3. I re-ran the relevant tests fresh this round (11 pass) and nothing in Round 5 touched `html_text.py`/`normalize.py`. The prior revert was a citation defect, not a false claim — but the row still needs the citation fixed, not just re-asserted. | Cross-round evidence above; `docs/reviews/RUBRIC_TRANSITIONS.md` row 27 |
| Payload robustness (out-of-rubric) | R-SEC-006/007 close for the literal-dict/direct-construction path measured; R-SEC-021 reopens the same DoS class for a `Mapping` input and should be fixed, not merely documented, since it is a one-line fix (`isinstance(..., Mapping)`). | R-SEC-021 |
| Gate reliability (out-of-rubric) | The disk-write guard's false-positive fix (R-SEC-017) held against an independent 167-line sweep — genuine improvement. The new seventh guard repeats the pattern this review chain keeps finding: real coverage on the claimed shape, an undocumented bypass one step past it (R-SEC-022), and a documentation gap inherited silently from its sibling guard (R-SEC-024). R-SEC-023 (chained assignment) is the most consequential of this round's new findings because it is completely ordinary code and affects every guard built on `_populate`. | Execution record above |

**Overall:** three Part-A findings verified closed (with one, R-SEC-006, closed narrower than
claimed); four Part-B mediums verified closed, matching their stated scope precisely including
the R-SEC-017 trade; the new seventh guard does what it claims for its claimed shapes and has
one real functional bypass plus inherited documentation gaps. Five new findings, all MEDIUM or
LOW, none BLOCKER/HIGH — consistent with "exactness rather than firefighting" for this round.
