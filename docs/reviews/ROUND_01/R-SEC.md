# R-SEC — Round 1 Security & Privacy Review

**Reviewer:** R-SEC (fresh instance, did not write this code) · **Date:** 2026-08-31
**Scope:** WS-00, WS-19, WS-01, WS-03 (auth/egress touchpoints), WS-07, per `WORK_ORDER.md`.
**Method:** execution only, per `AGENT_LOOP.md` §4/§7. `HANDOFF.md` claims were not trusted;
every claim below was reproduced by running code. Baseline: `make check` reproduced clean
(ruff, `ruff format --check`, mypy strict/55 files, `pytest -q -m "not network"` = 199 passed,
`python -m tools.guards` clean). Probe scripts live under `/tmp/.../scratchpad/`; no project
source or test file was modified.

---

## Findings

### BLOCKER
None.

### HIGH

**R-SEC-001**
Severity: HIGH
Rubric: SEC-01, SEC-03, SEC-05, SEC-08 (guard is these criteria's enforcement mechanism)
Location: `tools/guards/sweeps.py` (all six guards)
Reproduction: four files under `/tmp/.../scratchpad/secreview_bypass/`, run with
`uv run python -m tools.guards <that dir>` — 0 violations reported for all four. Contents
(condensed): (a) `importlib.import_module("mailweave" + "_harness")` then
`globals()["se"+"ed"+"_map"] = getattr(_mod, "SEEDER_SCOPE", None)`; (b)
`DESTRUCTIVE_SCOPE = "https://mail.google.com" + "/"` and
`SEND_ENDPOINT = "gmail/v" + "1/users/{userId}/messages/send"`; (c)
`importlib.import_module("open" + "ai")` with `path = "chat/completio" + "ns"`; (d)
`Path(out_path).open("w", encoding="utf-8").write(body_clean)` and
`os.write(fd, body_clean.encode())` to write a mail body to disk.
Expected: each is exactly what its guard's docstring says it exists to catch (harness import,
destructive scope, undeclared endpoint, generative client, unaudited write).
Actual: `run_all()` returns `[]` for all four. Root cause: `ground_truth_sweep`,
`scope_literal_sweep`, `gmail_path_sweep`, `generative_client_sweep` all match one whole AST
string-`Constant` — ordinary string concatenation (a natural f-string/"build the URL from
parts" refactor, not obfuscation) defeats all four. `forbidden_imports` and
`generative_client_sweep`'s import check only see `ast.Import`/`ast.ImportFrom` —
`importlib.import_module(...)` is invisible to both. `unaudited_disk_write_sweep` matches
`.write_text`/`.write_bytes`/`json.dump` and a bare `open(...)` **name** call only —
`Path(...).open(...)` (`ast.Attribute`, `.attr == "open"`) and `os.write` are unchecked shapes.
Required fix: constant-fold `ast.BinOp(Add)` chains and f-string segments before matching;
detect `importlib.import_module`/`__import__` call arguments in the import guards; add
`.open(...)` (any expression) and `os.write` to `_WRITE_CALLS`. This needs no sophistication
to trigger by accident — guard 6 is `HANDOFF.md` §3.7's own stand-in for the SEC-05/SEC-06
privacy audit, and guards 1/3/5 are the sole CI evidence for SEC-01/03/08's "structural, not a
matter of care" claims.

**R-SEC-002**
Severity: HIGH
Rubric: INJ-04 ("failures must be safe, not hangs" per the review brief; D.4a 5)
Location: `server/src/mailweave/content/html_text.py::_extract_selectolax`
Reproduction: `html_to_text("<div>"*N + "hi" + "</div>"*N, HtmlParserName.SELECTOLAX)` for
N = 10k/20k/40k/60k.
Expected: an ordinary, boundedly-sized HTML email body processes in well under a second, or the
pipeline declares a cap the way it does for MIME depth/part count (`MIME_DEPTH_CAP`,
`MIME_PART_CAP`).
Actual: wall-clock time scales quadratically with nesting depth (measured, this box):
N=10,000 → 0.32s; N=20,000 → 1.20s (3.8×); N=40,000 → 4.83s (4.0×); N=60,000 → 10.6s. There is
no depth cap anywhere in `html_text.py`. A single crafted HTML email body of roughly 0.5–1 MB
(trivially within Gmail message-size limits, no attacker infrastructure required) reaches
100,000–200,000 nested tags and, by this scaling, tens of seconds to low minutes of single
message processing time — a real hang, not a theoretical one. Separately, at extreme depth the
`lxml.html` fallback parser silently returned `text=""` (the "hi" payload vanished) with **no**
declared `Reduction` — content vanished with none of the `HTML_TO_TEXT`/`HIDDEN_CONTENT`
accounting the rest of this codebase insists on for every other removal
(`reductions.py`: "a reduction record with nothing in it is a silent reduction").
Required fix: cap DOM/tag nesting depth (or total node count) in both extractors before or
during the walk, declare the cap the way MIME depth/part caps are declared, and route the lxml
"parse produced nothing" case through a declared reduction or an explicit
`ContentProcessingError` rather than a silent empty string.

### MEDIUM

**R-SEC-003**
Severity: MEDIUM
Rubric: SEC-04
Location: `server/src/mailweave/auth/tokenstore.py::TokenStore.save`
Reproduction: pre-create `credentials.json` at mode `0o644` (simulating a stale file from a
prior run, a misconfigured deploy, or any process that touched the path first), call
`store.save(creds)`, and raise an `OSError` inside a patched `Path.chmod` right after the
`json.dump` write completes (simulating SIGKILL/OOM-kill/disk-full between the write and the
permission fix). Result: the file is left on disk at **mode 0644**, containing the refresh
token in full.
Expected: SEC-04's bar is "a leak requires more than reading a log"; a credential file should
never be observable in a readable state.
Actual: `os.open(path, O_WRONLY|O_CREAT|O_TRUNC, TOKEN_FILE_MODE)`'s `mode` argument is applied
by the kernel **only when the file is newly created** — for a path that already exists, the
file keeps its prior permission bits through the write, and `save()` only forces `0600` via an
explicit `.chmod()` call *after* the full `json.dump`. The existing test
(`tests/test_auth_and_config.py::test_the_file_is_never_briefly_world_readable`) covers only a
**fresh** file under a permissive umask (already safe by construction, since `0600` has no
group/world bits for umask to fail to strip) — it does not cover a pre-existing permissive
file, so this gap has no regression test.
Required fix: write to a temp file in the same (0700) directory, `os.open` it with the
requested mode, write, `fsync`, then `os.replace()` it onto the final path — standard atomic
secure-write pattern — so the final path never exists in an intermediate permission state.

**R-SEC-004**
Severity: MEDIUM
Rubric: SEC-07
Location: `server/src/mailweave/net/egress.py::check_url`
Reproduction: `check_url("https://xn--gmailgoogleapis-3ye.com/")` and one other malformed
`xn--` host.
Expected: per the module's own docstring, "Raise `EgressBlocked` unless `url`'s host is on the
allowlist" — implying `EgressBlocked` is the only failure mode a caller need handle.
Actual: `parsed.host` triggers `idna.decode()` internally, which raised an **uncaught**
`idna.core.InvalidCodepoint`, not `EgressBlocked`:
```
idna.core.InvalidCodepoint: Codepoint U+01E8 at position 10 of 'gmailgoogǨleapis' not allowed
```
The request still never reaches the inner transport in this case (verified: it fails before
`self._inner.handle_request(...)` is called), so this is not a live bypass — but it is an
undocumented, un-typed error surface. Code that follows the module's own contract and catches
only `EgressBlocked` around a `client.get(...)` call will see this propagate as an unhandled
exception instead.
Required fix: wrap the `parsed.host`/`parsed.scheme` access in `check_url` in a
`try/except Exception` and re-raise as `EgressBlocked`, so every rejection path is the one
type the rest of the codebase is built to expect.

**R-SEC-005**
Severity: MEDIUM
Rubric: INJ-04 (hidden-construct coverage)
Location: `server/src/mailweave/content/html_text.py::_strip_invisible_chars`,
`server/src/mailweave/content/normalize.py::normalise`
Reproduction:
```python
rlo = "Invoice_‮exe.cod‬_final.pdf"
normalise(rlo).text == rlo   # True — byte-for-byte unchanged
```
Expected: `HiddenConstruct` names ten hiding techniques (`ZERO_WIDTH` among them) precisely
because MailWeave's content pipeline treats "text that displays differently than it reads" as
an injection surface worth flagging.
Actual: `_strip_invisible_chars` strips zero-width joiners/spaces/BOM but not Unicode
bidirectional-control characters (U+202A–E, U+2066–2069, U+200E/F), and NFKC normalisation
does not remove them either — they pass through the entire pipeline into `body_clean`
unchanged and unflagged. Given the product's stated purpose (handing `body_clean` to a
downstream LLM/agent), an unstripped RLO/LRO override is a known technique (filename/text
spoofing, "Trojan Source") for making body text display in an order different from its true
character sequence — exactly the class of thing `HiddenConstruct` exists to catch, just not
one of the ten kinds tracked.
Required fix: add bidi-control stripping (or at minimum flagging, mirroring `ZERO_WIDTH`) to
`_strip_invisible_chars`, with a new `HiddenConstruct` member and a declared `Reduction`.

### LOW

**R-SEC-006**
Severity: LOW
Rubric: INJ-04 / D.4a (performance, not correctness)
Location: `content/mime.py::walk` vs. `content/payload.py::MessagePayload`
Reproduction: a synthetic Gmail payload with 200,000 sibling leaf parts. `model_validate`
took 1.7s, `process_message` a further 4.5s (peak RSS ~420MB), even though
`MIME_PART_CAP = 64` caps the *walk*, because it doesn't cap the prior Pydantic construction
of the payload tree. Not a hang at the depth tested and Gmail's API practically bounds part
counts, so LOW not MEDIUM — noted per the brief's "blow up memory" probe. Fix (optional):
check the raw shape's part count against a ceiling before `model_validate`.

**R-SEC-007**
Severity: LOW · Rubric: none — out-of-rubric robustness note
Location: `content/payload.py` (`Part` recursive model)
Reproduction: a payload nested >~2,000 `parts` deep raises `pydantic.ValidationError`
(Pydantic's own recursion guard) from `model_validate`, not a `RecursionError` and not the
module's own `ContentProcessingError`. Already safe (no crash/hang) but a foreign, untyped
exception for a future Gmail-client caller — noted so WS-02 catches it explicitly.

---

## Execution record

Every attack attempted, verbatim, with outcome. ALLOWED/CRASH entries are findings above;
everything else is a confirmed-blocked or confirmed-safe result.

### 1. Egress allowlist (`net/egress.py`, via `check_url` and the full transport)
| Attempt | Result |
|---|---|
| `evilgmail.googleapis.com` (prefix) / `gmail.googleapis.com.evil.tld` (suffix) / trailing dot | **BLOCKED** (all three) |
| `GMAIL.GOOGLEAPIS.COM` / `Gmail.Googleapis.Com` (case) | ALLOWED — correctly normalises to the real host, not a bypass |
| `https://gmail.googleapis.com@evil.tld/` and `%2F@evil.tld/` (userinfo authority) | **BLOCKED** — host correctly resolves to `evil.tld` |
| `https://xn--gmailgoogleapis-3ye.com/` and one more malformed-punycode host | **CRASH** — `idna.core.InvalidCodepoint`, not `EgressBlocked` (R-SEC-004); request still not forwarded |
| IP literal `198.51.100.5`, IPv6 `[::1]` | **BLOCKED** (both) |
| `http://gmail.googleapis.com/...` (non-https to allowed host) | **BLOCKED** |
| `https://gmail.googleapis.com:8443/...` (explicit port) | ALLOWED — host check ignores port; not exploitable, host is still the real Google host (informational) |
| bare `gmail.googleapis.com` / `https:gmail.googleapis.com/x` (scheme-less/malformed) | **BLOCKED** |
| `gmail。googleapis。com`, `gmail．googleapis．com` (ideographic/fullwidth full stops) | ALLOWED — IDNA correctly folds these to the real host; not a bypass |
| `%67mail.googleapis.com` (percent-encoded host char) | **BLOCKED** |
| tab / zero-width space injected into the host | **BLOCKED** at URL-parse time by httpx itself (`InvalidURL`) |
| Redirect: allowed host returns `302` to `https://evil.tld/steal`, `follow_redirects=True` | **BLOCKED** — the redirect target is re-checked by the transport; the evil request never reached the inner transport |
| `httpx.URL(...).copy_with(host="evil.tld")` fed directly to `check_url` | **BLOCKED** |

### 2. Credentials, tokens, PKCE
| Attempt | Result |
|---|---|
| Server construct a `ClientDescriptor(role=SEEDER, ...)` | **BLOCKED** — `ConfigError` at construction, unconditionally |
| Fresh token write, umask=0 | Correct: `0600`/`0700`, forced regardless of umask |
| `load()` on a `0644` token file | **BLOCKED** — `TokenStoreError`, no silent repair, file left untouched at `0644` |
| Pre-existing `0644` file + `save()` + simulated crash mid-write | **Refresh token left on disk at `0644`** (R-SEC-003) |
| `grep get_secret_value(` + `doctor`/`purge` CLI failure output | Two call sites only (disk write, env-leak self-check); no secret in any printed string |
| PKCE: verifier entropy / challenge method / state check / `error=` param | 64 bytes; `S256` unconditional; `secrets.compare_digest`; `error=` raises before state/code check |

### 3. Untrusted content parsing
| Attempt | Result |
|---|---|
| 10,000- and 4,000-deep nested multipart, fed to `MessagePayload.model_validate` | **Clean `pydantic.ValidationError`** — Pydantic's own recursion guard, no crash/hang (R-SEC-007, LOW) |
| 200,000 sibling MIME parts | Completes in ~6.2s total, ~420MB peak RSS, no crash (R-SEC-006, LOW) |
| 5MB single RFC 2047 encoded-word in one header | Decodes in 0.16s, no hang |
| Malformed base64url body; unknown/bogus declared charset; raw byte range 0–255 | Clean `UndecodableBody` / falls through the charset ladder to `cp1252`/replacement decode — no crash, every case |
| Unicode bidi override (RLO/PDF) in body text | **Passes through unflagged** (R-SEC-005, MEDIUM) |
| `<script>`/`<noscript>`/`<template>`; `display:none`/`visibility:hidden`/`color==background` | **Removed from visible text**, both parsers; style-hidden text also flagged as `HIDDEN_CONTENT` |
| DOCTYPE external entity (`<!ENTITY xxe SYSTEM "http://evil.tld/...">` + `&xxe;`); nested-entity "billion laughs" (8 levels) | **Not resolved/expanded** — literal in output, no network call, sub-millisecond, both parsers |
| 10k/20k/40k/60k-deep nested `<div>` (no attributes, no MIME layer) | **Quadratic time**: 0.32s / 1.20s / 4.83s / 10.6s — real hang risk at realistic sizes (R-SEC-002, HIGH); `lxml` fallback silently lost all content at this depth with no declared reduction |

### 4. AST guards
| Attempt | Result |
|---|---|
| `run_all()` over the shipped `server/src` tree | Clean, 0 violations (matches `HANDOFF.md`) |
| Split-literal ground-truth reference + dynamic harness import | **0 violations — bypass confirmed** (R-SEC-001) |
| Split-literal destructive scope + undeclared endpoint literal | **0 violations — bypass confirmed** (R-SEC-001) |
| Dynamic `openai` import + split `chat/completions` literal | **0 violations — bypass confirmed** (R-SEC-001) |
| `Path(...).open("w")` and `os.write(fd, ...)` writing mail body to disk | **0 violations — bypass confirmed** (R-SEC-001) |
| Planted-violation regression tests (`tests/test_guards.py`) | All pass — guards correctly catch their *documented* shapes; the gap is coverage, not correctness on the cases they were built for |

### 5. Privacy (OD-4 / A.3)
| Attempt | Result |
|---|---|
| Regex scan of `tests/`, `server/` for `@<provider>.com`-shaped addresses outside `example.*`/`invalid`/`acme`/`mailweave` | **No matches** — no real-looking personal email addresses found |
| Read `tests/fixtures/mime_kit.py`, `envelope_kit.py` headers/docstrings | Explicitly self-documented as synthetic, RFC-constructed, "nothing sanitised from a real mailbox" |
| Write-path audit guard (`unaudited_disk_write_sweep`) against the real tree | Clean — only `auth/tokenstore.py` writes; correct on the current tree |
| Write-path audit guard against adversarial code | **Bypassed** (R-SEC-001) — the guard is not yet a reliable enforcement mechanism for SEC-05 going forward |
| Offline-suite network block (`tests/conftest.py`) | Confirmed present, autouse, blocks `socket.connect`/`connect_ex`/`create_connection`/`getaddrinfo` for every non-`@pytest.mark.network` test |

---

## Per-criterion recommendations (`RELEASE_RUBRIC.md`)

| Criterion | Recommendation | Basis |
|---|---|---|
| SEC-01 | **NOT YET PASS** | One scope literal today, independently enforced at runtime by `config.py`/`clients.py` — solid. But its stated CI-gate acceptance doesn't hold against ordinary future code (R-SEC-001). Fix guard, re-verify. |
| SEC-02, SEC-06 | Correctly not claimed | No tool surface / trace sink built yet; out of round-1 scope |
| SEC-03 | **NOT YET PASS** | Server-side seeder refusal (`ClientDescriptor`) verified unconditional. CI evidence the destructive scope/harness import can never land in server code is bypassable (R-SEC-001). |
| SEC-04 | **NOT YET PASS** | Mode enforcement, refuse-not-repair, PKCE, secret-in-logs all solid. R-SEC-003 (non-atomic overwrite of a pre-existing permissive file) is a reproduced counterexample; needs a fix and a test. |
| SEC-05 | **NOT YET PASS** | Current tree writes nothing but the token store (verified). Its guard (`HANDOFF.md` §3.7's stand-in) is bypassable (R-SEC-001). |
| SEC-07 | **NOT YET PASS** | Strongest area this round: exact two-host match, https-only, redirects re-checked; every spoofing technique tried was blocked or resolved to the real host. Missing to meet the rubric text: a **cold-start network capture** and a **port scan** (neither exists, per `HANDOFF.md`). Also fix R-SEC-004. |
| SEC-08 | **NOT YET PASS** | No model/routing code exists to violate this; its guard is bypassable (R-SEC-001), same as SEC-01/03/05. |
| INJ-04 | **NOT YET PASS** | Core intent solid and verified: no network, no entity resolution, script/style/head/comment stripped, 4/5 style-hiding techniques flagged. R-SEC-002 (nesting hang + silent content loss) and R-SEC-005 (bidi unflagged) must be fixed first. |
| NFR-01 | **PASS** | `make check` reproduced clean, `MAILWEAVE_CI=1`, no provider keys, no network beyond `uv sync`. |
| NFR-04 | **PASS** | `uv sync --frozen` + full `make check` succeeded on this fresh environment, matching `HANDOFF.md`. |
| REG-03 | Not primarily reviewed | R-ARCH's domain; no benchmark special-casing observed in what was read |
| REG-04 | **PASS** (privacy angle) | No real-looking personal addresses in any fixture; fixtures self-documented synthetic; offline suite confirmed. Defer rest of REG-04 to R-ARCH/R-DISC. |
