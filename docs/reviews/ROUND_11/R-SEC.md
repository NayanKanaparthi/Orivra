# ROUND 11 — R-SEC review

**Reviewer:** R-SEC, independent instance, 2026-09-01. Verified by execution per
`AGENT_LOOP.md` §4/§7. `.venv`/caches wiped, resynced. `mailweave.__file__` and
`mailweave_harness.__file__` both resolve under `/root/mailweave/*/src/...` (correct local
tree). Source/tests untouched; probes ran in `/tmp/rsec_probes/*.py`, named below.

**Environment.** `ruff check`/`ruff format --check` clean, 125 files. `mypy --strict`
clean, 99 files. `pytest -q -m "not network"`: **1,646 passed** (build prints no summary
line; recounted via `--collect-only` per-file totals, matches handoff). `guards` 7 clean
over `server/src`. `rubric_status.py --check`: 7 PASS/0 FAIL/0 BLOCKER/106 NOT TESTED, 11
transitions — unchanged, as required.

## Priority 1 — account pinning (most thorough, as instructed)

Three controls in `pinning.py`: (1) Google Testing-status/test-user allowlist — **not
establishable here**, a Console setting, not executable code, and the review's biggest gap:
the *strongest* control is trusted on prose alone; (2) `verify_seed_account`/`SeedSession`,
attacked below; (3) import-side CI guard — **verified live**: planted
`import mailweave_harness` and the destructive scope literal in a scratch tree, both guards
(`forbidden_imports`, `scope_literal_sweep`) fired, matching
`test_the_server_package_still_cannot_import_the_harness` /
`test_the_destructive_scope_literal_is_absent_from_server_code`.

**Control 2, attacked directly.** Wrong/unobservable/empty account → all correctly raise
`SeedAccountMismatch` (`test_harness_pinning.py` re-run plus my own re-derivation).
**Direct construction bypasses the check entirely:**
`SeedSession(address="owner-real-mailbox@gmail.com", scopes=("https://mail.google.com/",))`
builds a valid session — zero calls to `getProfile`, zero use of the private
`_SESSION_TOKEN`, no private name reached for at all (`attack_pinning_direct_
construct.py`). The module's docstring/test claim the residual is "reaching for the
private name," the disposition seal's accepted R-ORCH-002 shape. **That overstates it: no
private name is needed, only public fields.** Reach-a-destructive-op-without-a-session is
moot: grepped both trees for `insert(`/`import(`/`trash(`/`delete(`/`batchDelete`, **zero
call sites** anywhere — nothing destructive exists yet to reach. Swap-credentials-after-
pinning: `SeedSession` holds only `address: str` and `scopes: tuple[str, ...]`, no binding
to the client/token instance that produced it — nothing stops profiling client A and later
pairing the session with client B.

**Judgement: not BLOCKER.** No code path connects a forged/misbound session to an actual
Gmail write this round — the invariant holds today on controls 1+3 alone, not on 2. Control
2 is the piece code could make airtight and currently does not. Must be hardened **before
WS-16** wires `SeedSession` to a real delete/insert call — at that point this stops being
contrived.

**Establishable now:** mismatch/unobservable/empty rejection, import direction — both
established by execution. **False on execution:** "`SeedSession` unforgeable" — it is
forgeable. **Not establishable here at all:** whether Google's Console allowlist really
blocks the personal mailbox.

## Priority 2 — scope verification: holds, both directions

Built real `TokenGrant`s directly (not mocking `verify_granted_scopes`), drove six cases
(`attack_scope_verification.py`): exact match (pass); **narrower** grant → refused,
`missing=[...]`; **broader** grant including `https://mail.google.com/` (the case that
matters most) → refused, `unexpected=[...]`; no `scope` field → `ScopeUnverifiable`, fails
closed; `scope=""`/whitespace → same fail-closed path; case-differing scope → refused
(safe-direction false negative). `run_login` wires the check before `fetch_address`/
`store.save` — confirmed by reading, ordering is real. Refresh's "omitted scope =
unchanged, not unknown" is intentional (a prior grant was already verified), not a silent
skip. **Verdict: fully holds**, verified independently of the shipped tests.

## Priority 3 — secret handling

Canary (`test_no_secret_survives_into_a_traceback_on_any_failing_step`) is real: 5 forced
failures, greps `traceback.format_exc()` for all 4 secrets.

**7 additional forced failures** (`attack_secrets_beyond_canary.py`,
`attack_perm_error.py`, `attack_secretstr_field_invalid.py`), secrets searched in full
tracebacks: network failure mid-exchange; malformed non-JSON and malformed-shape token
responses; corrupt (invalid-JSON) token file; refresh-time network timeout; **real**
`PermissionError` via `chattr +i` (immutable, unbypassable even by root) on `save()`/
`purge()`; `os.fsync` failure mid-write — **no leak in any of the seven**.

**One real leak found.** A stored `refresh_token` field corrupted into a nested structure
(failing Pydantic's type check) while holding a real-looking value makes `ValidationError`
render a **truncated-but-substantial fragment** (intact prefix/suffix) via
`input_value=...`, embedded verbatim by `TokenStore.load()` into `TokenStoreError`.
Reachable via `preflight.__main__` → `StoredTokenProvider.access_token()` → `store.load()`,
unhandled there (`auth login` never calls `load()`, unaffected). R-SEC-043.

**Subprocess/shell:** zero matches for `subprocess|os\.system|Popen|shell=True` in either
tree — nothing shells out, no process-argument-list exposure possible. **Browser:** zero
matches for `webbrowser`, confirming "no browser is opened."

## Priority 4 — egress and error text

**`error.message` genuinely discarded.** `_error_reason` reads only `error.errors[].reason`
/`error.status` through the anchored-slug filter, never `error.message` — confirmed against
`test_no_part_of_a_gmail_error_body_reaches_a_mailweave_error_string` (plants an address +
"the NDA we discussed", asserts none of it in `!r`/`!s`/`.args!r`).

**Query text — a second route exists, now live for the first time.** `ScanScopeEntry.q`
carries the raw, unhashed query onto the wire via `EnvelopeBuilder`, and
`GmailClient.list_messages` (this round's deliverable) now populates it. Round 10 accepted
this field because "no route from mail content today" — **that rationale is now false**.
Not yet live with real user text (no retrieval rung/MCP surface calls it with anything but
system-controlled strings, confirmed by reading every call site) — a correction to round
10's stale note, not a new finding.

**Allowlist attacked directly** (`attack_egress_allowlist.py`): evil host, http-not-https,
subdomain-suffix trick (`gmail.googleapis.com.evil.com`, same for the OAuth host) — all
blocked before reaching the inner transport (proved with a `MockTransport` that prints if
invoked; never does). Mixed-case host allowed — safe, httpx normalises casing. **Port not
checked** — `https://gmail.googleapis.com:1337/` passes; not reachable today, no URL in the
repo carries a port (R-SEC-044). **No new unwrapped client**: zero `httpx.Client(`/
`httpx.AsyncClient(` outside `net/egress.py`; planted one in a scratch tree and the
`unwrapped-http-client` guard fired on both sync and async forms.

**Two bugs found while chasing this** (full detail in Findings): (1) `run_probes()`'s
first, unconditional line calls `sample_mailbox`, whose default `query=""` violates
`ScanScopeEntry`'s `min_length=1` — reproduced end-to-end (real client + fake transport,
one unrelated probe selected) as `pydantic.ValidationError` before any probe body runs, for
every invocation; the harness cannot complete a single live call today (R-SEC-041,
R-GMAIL/R-ARCH domain). (2) `assert_record_is_content_free`'s recursion freezes `key` at
the first dict level, so a string nested under one of the 7 "our prose" exempt keys
inherits the exemption at any depth — proved both directions; not reachable via any of the
6 shipped probes today, all confirmed to emit only flat strings there. Same class as
R-SEC-032 (HIGH, round 9): a "checkable by shape" OD-4 backstop with a shape-dependent
hole (R-SEC-042).

## Findings

```
ID: R-SEC-039  Severity: HIGH  Rubric: none — SEC-03 account pinning
Location: harness/src/mailweave_harness/pinning.py (SeedSession)
Repro: SeedSession(address="owner-real-mailbox@gmail.com", scopes=(...,)) builds fine —
  no getProfile call, no private name referenced.
Expected: bypass requires "reaching for the private name" (module's own claim).
Actual: the public constructor alone suffices. Inert this round — no consumer exists.
Required fix: before WS-16, correct the claim, or harden so forgery needs a private path.
```
```
ID: R-SEC-040  Severity: MEDIUM  Rubric: none — SEC-03 account pinning
Location: harness/src/mailweave_harness/pinning.py (SeedSession)
Repro: SeedSession carries only strings, no binding to the profiled client/token instance.
Expected: "swap credentials after pinning" structurally prevented.
Actual: nothing stops pairing a session minted from client A with a call on client B.
Required fix: WS-16's call must reuse the minting client, or SeedSession must bind identity.
```
```
ID: R-SEC-041  Severity: HIGH  Rubric: none — cross-domain (R-GMAIL/R-ARCH), found via Pri.4
Location: harness preflight/measure.py (sample_mailbox); server envelope/wire.py
  (ScanScopeEntry.q, min_length=1)
Repro: run_probes(client, selected=[<any one probe>]) raises pydantic.ValidationError on
  its first, unconditional call to sample_mailbox (default query=""), before any probe runs.
Expected: "every preflight probe is runnable" (round 11 exit condition).
Actual: mailweave-preflight --run cannot complete a single call, ever. Untested path.
Required fix: sample_mailbox's default query must satisfy min_length=1 while meaning "list
  everything" (e.g. "in:anywhere").
```
```
ID: R-SEC-042  Severity: HIGH  Rubric: OD-4 — no mail text in a record without approval
Location: harness preflight/record.py (assert_record_is_content_free)
Repro: assert_record_is_content_free({"notes": {"raw_snippet": <mail body>}}) does not
  raise; the same content under {"totally_not_prose": {...}} correctly raises.
Expected: "checkable by shape" (module's own docstring), for any shape.
Actual: key tracking freezes at the first dict level, so nesting under an exempt top-level
  key inherits the exemption at any depth. Unreachable via the 6 shipped probes today.
Required fix: track the field-name chain at every level, or restrict the exemption to
  string-typed values only.
```
```
ID: R-SEC-043  Severity: MEDIUM  Rubric: SEC-04 — no secret in log/error/traceback/file
Location: server/src/mailweave/auth/tokenstore.py (StoredCredentials.model_validate, load())
Repro: a credentials.json whose refresh_token is a secret wrapped in a dict (type-invalid)
  makes load() raise TokenStoreError embedding Pydantic's truncated-not-redacted
  input_value=..., via preflight's StoredTokenProvider (auth login never calls load()).
Expected: no refresh token, even fragmentarily, in an exception message.
Actual: a substantial fragment reaches the message string under this corruption shape.
Required fix: catch ValidationError in load() and report field names only, never Pydantic's
  default error text, for an invalid SecretStr field.
```
```
ID: R-SEC-044  Severity: LOW  Rubric: SEC-07 egress allowlist, hardening only
Location: server/src/mailweave/net/egress.py (check_url)
Repro: check_url("https://gmail.googleapis.com:1337/") does not raise; port is not checked.
Expected: the allowlist is the project's sole stated technical egress control.
Actual: a non-443 explicit port on an allowlisted host passes. Not reachable today — no URL
  in the repo carries a port.
Required fix: refuse a non-default explicit port, or document why it is out of scope.
```

## Recommendations, per criterion

- **Account pinning (SEC-03).** Don't gate on R-SEC-039/040 — neither reaches an actual
  write today. Treat both as a hard precondition on WS-16's design. Google's Testing-mode
  control is **unverifiable by any reviewer without live Console access** — don't let it
  be implicitly trusted for reading well in prose.
- **Scope verification (SEC-01).** Establishable now, both directions plus no-`scope`,
  independent of the shipped tests. Remaining: whether Google's real endpoint ever omits
  `scope` in practice (G8/PF-17) — needs the live run.
- **Secret handling (SEC-04).** Canary is real. Fix R-SEC-043 before the live run.
- **Egress/error text (SEC-07, AD A.11).** `error.message` discard holds. **Fix R-SEC-041
  before any live run** — the harness cannot complete a single probe otherwise. Fix
  R-SEC-042 before any probe gains structured notes; R-SEC-044 is a nice-to-have.

**Overall: no BLOCKER.** R-SEC-039/040/042 are real but inert. **R-SEC-041/043 are not** —
both sit in the path of the owner's imminent first live run; fix first.
