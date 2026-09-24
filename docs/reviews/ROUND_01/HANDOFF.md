# ROUND 01 — Implementer handoff

**From:** implementer agent · **Date:** 2026-08-31
**Work order:** `docs/reviews/ROUND_01/WORK_ORDER.md` (WS-00, WS-19, WS-01, WS-03, WS-07)
**Reviewers gating this round:** R-ARCH, R-DISC, R-SEC, R-RETR

> Per `AGENT_LOOP.md` §2.2 this document is an unverified hypothesis, and the "not done /
> not verified" sections below are as much of the deliverable as the code. I have marked
> **no** rubric criterion PASS; `tools/rubric_status.py` reports all 113 as `NOT TESTED`,
> which is where they stay until a reviewer reproduces the evidence.

---

## 1. How to run it

```bash
uv sync --all-packages --extra dev     # Python 3.12+, uv; no keys, no credentials, no network needed
make check                             # lint + format + types + offline tests + guards + gate integrity
```

Individually: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
`uv run pytest -q -m "not network"`, `uv run python -m tools.guards`,
`uv run python tools/rubric_status.py --check`.

Verified on a clean copy from the lockfile alone (`uv sync --frozen`): 199 tests pass,
ruff clean, mypy `strict` clean over `mailweave`, `mailweave_harness`, `tools` **and**
`tests` (55 files), all six source guards clean, gate-integrity check clean.

CI (`.github/workflows/ci.yml`) runs exactly those commands. A second, advisory job runs
`--gate` (PROC-01's "NOT TESTED blocks release"); it is expected to fail today and its
`continue-on-error` comes off at the release round.

---

## 2. What was built

### WS-03 — response envelope and partiality (`server/src/mailweave/envelope/`)

The centre of the round. Five modules:

| File | Contents |
|---|---|
| `vocab.py` | Closed vocabularies: `Role` (7), `Depth` (5), `Outcome` (3), `NotTriedWhy` (5), `WithheldCap`, `BudgetCapName`, `ToolName` (the 4 tools), `Trust`, `Sufficiency` |
| `reasons.py` | `Reason` as a **discriminated union of mechanisms**, not a free string |
| `wire.py` | Every sub-object of D.2, each with the contract obligation as a validator |
| `disposition.py` | The hit ledger, the set difference, the certificate |
| `response.py` | `Envelope`, and the invariants it refuses to be built without |
| `builder.py` | The only supported path to an `Envelope` |

**The withheld invariant, and how it is enforced.**

`DispositionLedger` accumulates `H` from the three A.7a clauses — `record_list_page`
(H-lex, at *any* rung, which is how the L2/L3 relaxation queries and the L5 participant
probes of ADV-109 are covered), `record_history_additions` (H-hist), `record_shortlist`
(H-sem, refusing a shortlist larger than the declared `k`). Caps call `note_withheld` to
supply a *reason*; they never decide membership.

`certify(disclosed)` computes `withheld := H − disclosed` as a set difference and refuses
three residues, not one:

1. an ID in `H − disclosed` with **no cap note** → a cap dropped a hit silently;
2. a cap note for an ID that **is disclosed** → depth reduction is not omission (A.7a),
   so a withheld record for a stub row is a false statement;
3. a cap note for an ID **not in `H`** → a rung fetched IDs without recording them, so
   `H` is under-counted and the invariant would otherwise pass vacuously.

All three raise `DispositionInvariantError`. They **raise explicitly rather than
`assert`**, because A.7a's pseudocode uses `assert` and `python -O` deletes it;
`tests/test_invariant_under_optimised_python.py` runs the failing case in a real `-O`
subprocess to prove the check survives.

Three things make this structural rather than conventional:

- `EnvelopeBuilder.build()` computes `disclosed` by walking the sources **it is actually
  shipping** — it is not a caller-supplied argument. `test_disclosed_ids_are_read_from_the_payload_not_from_the_caller`
  shows a ledger that certifies happily while the builder still refuses.
- `Envelope` requires a `DispositionCertificate`, which can only be minted inside
  `certify` (a module-private capability token). Constructing one directly raises.
- The certificate carries a **digest of the exact disclosed set** it was computed
  against, so a certificate cannot be lifted from an honest small response and attached to
  a larger payload.

`scan_scope` and `shortlist` on the response are taken **from the ledger**, not from the
caller, so the response's account of what it scanned cannot drift from the definition of
`H` it was accumulated under.

**OD-2, enforced in two places.**

`RetrievalReport` rejects `outcome: not_found` when any `not_tried[].why` is in
`{budget, cap, timeout, error}` or when `budget_caps_hit` is non-empty; `not_applicable`
does not block. `Envelope` additionally rejects `not_found` when anything is withheld
(a withheld record *is* retrieved evidence), when any `scan_scope` entry has
`more_pages: true` (ids on unfetched pages were never examined, so no route was
exhausted), when a `matched` row is disclosed, or when `empty_diagnosis` is absent. The
`inconclusive` form of every one of those states is constructible — the rule removes the
dishonest response, not the honest one, and a test asserts that.

`tests/test_outcome_od2.py` includes a property test over arbitrary `not_tried`/cap
combinations asserting `not_found` is constructible **exactly** when OD-2 permits, with
the blocking vocabulary quoted from OD-2 rather than imported from the implementation.

**Other obligations turned into validators.** `included`/`included_as_stub` recomputed
from the payload (PART-01/02); `partial` computed, never asserted (PART-03, both
directions, including "no phantom remainder" on a complete thread); an incomplete source
without an affordance naming it is refused (R-07); collapsed runs must enumerate members
and their span must match their count (R-06/PART-05); `more_pages` without a widening
affordance is refused (GMAIL-04); a blocking `not_tried` entry without an affordance is
refused (AD-03); the three `empty_diagnosis` states are structurally distinct and the
fourth (incomplete *and* a named restore) is unconstructible (ADV-105); a zero-evidence
response must carry rungs, executed queries and a diagnosis (ROUTE-01); mail text must be
fenced with the response nonce and cannot contain it (R-09); the ceiling's overflow must
declare why; a budget clamp must be upward and land at or above the published floor;
`errors[]` may only carry D.11's in-band codes.

### WS-07 — content processing (`server/src/mailweave/content/`)

`payload.py` (typed Gmail payload tree) → `mime.py` (walk, depth cap 12 / part cap 64,
`text/plain` preferred with the unused alternative declared, attachment metadata rows) →
`decode.py` (base64url with padding restoration; charset ladder declared → utf-8 → cp1252
→ latin-1, ladder passed as a parameter) → `headers.py` (RFC 2047, undecodable words kept
verbatim and flagged, duplicates all retained with the count declared) → `html_text.py`
(selectolax, `lxml.html` fallback, hidden constructs removed and counted) → `quotes.py` →
`normalize.py` (NFKC, whitespace, recorded head truncation) → `pipeline.py`.

Every removal emits a `Reduction` from a closed `ReductionKind`, and `Reduction` itself
refuses a record that declares neither a size nor a count — a reduction record with
nothing in it *is* a silent reduction.

### WS-01 — config and credentials

`config.py` (scope set and egress allowlist are code constants a config file may not set;
`SecretStr`; over-permissive config files refused), `auth/tokenstore.py` (0600 in 0700,
mode set at `os.open` time so a permissive umask cannot widen it; reads refuse rather
than repair), `auth/profile.py` (both A.4 conditions; unset → personal; `getProfile`
failure → `AuthProfileUnderivable`, not a default), `auth/clients.py` (the server cannot
construct the seeder client at all), `auth/pkce.py` (S256 unconditional, loopback only,
state checked with `compare_digest`), `net/egress.py` (sync + async httpx transports that
refuse before any connection is attempted), `cli.py` (`doctor`, `purge`; `auth` refuses
with an explanation).

### WS-00 / WS-19 — scaffold, guards, loop machinery

`uv` workspace with `server/` and `harness/` as separate packages; ruff + mypy(strict) +
pytest; six AST-based source guards each with a planted-violation test; CI; seeded
`docs/reviews/FINDINGS_LEDGER.md`; new `docs/reviews/RUBRIC_TRANSITIONS.md`; and
`tools/rubric_status.py`, which parses the rubric's summary table *and* its criterion
blocks, cross-checks them, and fails if any criterion is `PASS` without a transition row
naming a reviewer domain and reproduction evidence. I did not edit `RELEASE_RUBRIC.md`.

---

## 3. Design decisions a reviewer should challenge

1. **`reason` is a closed typed union.** PART-07 forbids decorative rationales; a `str`
   field cannot. The wire keeps D.2's mechanical string (`field_serializer`) and adds
   `reason_detail` with the structured form. Cost: the row no longer round-trips from
   JSON, and `reason_detail` is a field D.2 does not list.
2. **`CollapsedRun.member_ids` is on the wire**, beyond D.2's `positions`/`count`. Without
   it, `disclosed` cannot be computed from the response, and EV-01's "a member of a
   declared collapsed run counts" is an assertion about data the response does not carry.
   IDs contain no mail content.
3. **`Source.included` follows contract R-05, not D.2's example arithmetic.** R-05 defines
   `included` as "the count included in this response" with `included_as_stub` the subset
   carried as stubs; D.2's sketch shows `included: 7, included_as_stub: 35, stated_total: 42`,
   in which `included_as_stub` is *not* a subset. I implemented the contract (included =
   every message present at any depth; included_as_stub ⊆ included) because PART-02 asserts
   the included set equals the payload. **This needs an orchestrator ruling**; if D.2's
   reading wins, one validator and one helper change.
4. **`talon` could not be pinned; the fallback shipped.** `talon` requires `cchardet`,
   which does not build on CPython 3.12 (`longintrepr.h` removed). D.4a §6 names
   `email-reply-parser` (MIT) as the fallback for exactly this case, and that is what is
   installed. Quality consequence is real and unmeasured — see §5.
5. **The ground-truth sweep is AST-based, not grep.** It checks identifiers, imports and
   non-docstring string literals. A grep for `harness` over `server/**` fails on prose
   that merely explains why the server does not touch the harness, and an un-passable gate
   gets disabled. Comments are not scanned at all, on the reasoning that a comment cannot
   read a file. A reviewer may reasonably want the cruder sweep as well.
6. **`import-linter` is not used.** The contract it would express (`server` ⊁ `harness`) is
   implemented as an AST import check that also covers `tools` and `tests`, with planted
   violations tested. That is a substitution of my choosing, not the plan's letter.
7. **The disk-write guard is the trace-content audit's stand-in.** No server module except
   the credential store may call `write_text`/`write_bytes`/`json.dump`/`open(w)`. It is
   cruder and stronger than the real audit, which needs WS-13's trace schema and sentinel
   canary to exist.
8. **`hidden_content` counts only constructs that removed readable text.** An HTML parser
   inserts an empty `<head>` into every document; counting that would make INJ-04's signal
   fire on every message. Tracking pixels are removed but not counted, for the same reason.
   INJ-04 could be read as requiring every hidden construct counted regardless.

---

## 4. What I did NOT do

In scope for the named workstreams, and absent:

- **No OAuth token exchange or refresh.** `pkce.py` builds and validates the parameters;
  nothing exchanges a code for a token or refreshes one, because that needs the HTTP client
  of WS-02. Consequently **GMAIL-06's refresh/expiry/re-auth paths are not exercised** —
  `auth_reauth_required` exists in the error vocabulary with no code path that raises it.
  The work order excluded the interactive consent step; it did not exclude refresh, and
  refresh is missing.
- **No live profile derivation.** `derive_profile` is a pure function with tests; the
  startup `users.getProfile` call that feeds it belongs to WS-02, so the fatal-startup path
  is tested only at the function boundary.
- **No watermark store.** `config.watermark_path` names the file; nothing reads or writes it.
- **No HMAC handle key / `key_epoch` machinery.** `StoredCredentials.key_epoch` is a stored
  integer and nothing else; handles are WS-06.
- **No `models.lock` with SHA-256 pins.** No model is loaded in this round, and inventing
  checksums I cannot verify would be fabrication. WS-08 must create it.
- **No `harness auth --refresh`, no seeder.** The harness package contains its scopes and
  the account-pinning abort, nothing more.
- **No A.9a degradation ladder.** `EnvelopeBuilder` enforces the ceiling by *raising* if the
  assembled response exceeds it without declaring self-truncation. It cannot degrade,
  because degradation is WS-11. So DISC-06 is half-built: the response can never silently
  exceed its ceiling, but nothing yet makes it fit.
- **`not_included_sources` and `Score` are types with no producer.**
- No retrieval rungs, no Gmail client, no MCP surface, no traces — later rounds, correctly.

---

## 5. What I could not verify

- **Anything involving real Gmail.** No credentials exist. Every MIME fixture is synthetic
  and written from the RFCs, so it is nastier than average real mail in some ways and
  certainly unrepresentative in others. GMAIL-02 is *not* satisfied by this round: it asks
  for real-mailbox messages, and I have none.
- **Quote and signature stripping quality.** `email-reply-parser` is regex-based; `talon`'s
  ML signature detection is absent. On my fixtures it is correct; on real mail with Outlook
  headers, top-posting variants, mobile signatures and non-English quote markers I expect
  materially worse recall, and I have no measurement. This is the most likely source of a
  future GMAIL-02/DISC-03 finding.
- **The egress property empirically.** `AllowlistTransport` refuses before connecting and is
  tested with a recording inner transport, but SEC-07 wants a network capture on a cold
  start in a two-host container. Not done.
- **That the whitespace-token estimate resembles the real tokenizer.** `measure_tokens` is
  explicitly *not* the pinned tokenizer of DISC-04/PF-6 — that bar is `[UNSET — register at
  G0]` and I refused to invent one. So ceiling enforcement fires against an estimate, and
  the estimate ignores map rows, the retrieval report and withheld records.
- **`charset_replacements` with a non-zero count on the shipped ladder.** Because the ladder
  terminates at latin-1, which cannot fail, the strict-decode path always succeeds and the
  replacement count is always 0 in production; the record currently declares a *fallback*
  rather than a *replacement*. The counting code is exercised by a test that passes a ladder
  that can fail. If D.4a §3 means the count to be reachable in production, the ladder needs
  to change, and that is a design question I did not want to answer unilaterally.

---

## 6. Where I think this is weakest

**First: `H` is only as complete as the callers that record into it.** The ledger guarantees
*everything recorded is accounted for*. It does not, and cannot from where it sits,
guarantee *everything fetched is recorded*. A future rung that calls `messages.list` and
never calls `record_list_page` shrinks `H`, and every check in this round passes vacuously —
which is precisely EV-01's deflationary degenerate strategy. The alien-note check catches
one narrow instance of this. My recommendation for WS-02, which I did not build and cannot
enforce from here: make the Gmail client physically unable to return a `messages.list`
result without a ledger, e.g. `list_messages(ledger, ...) -> ScanScopeEntry` returning the
recorded page rather than a bare ID list. **If a reviewer looks at one thing, look at this
seam.**

Second: the certificate's unforgeability is a Python convention. `_MINT_TOKEN` is a
module-private object; code that deliberately imports it can mint anything. The guard is
against accident and drift, not against a hostile implementer, and I do not claim otherwise.

Third: `Envelope`'s validators check the payload against *itself*. They are strong on
self-consistency (`included` vs rows, `partial` vs the evidence, withheld vs disclosed) and
say nothing about whether `stated_total` matches Gmail — that is GMAIL-03's job and needs a
mailbox.

Fourth: I wrote both the code and its tests, so the fixtures encode my understanding of the
inputs. The two defects hypothesis found during this round — a zero-size `hidden_content`
record from an implicit `<head>`, and the quote stripper silently discarding whitespace that
was neither quote nor signature — are the two I would not have found by hand, and both were
in exactly the "small silent reduction" class this project exists to eliminate. I expect more
of that class to remain.

---

## 7. Criteria I believe this round advances

Stated as belief, not status. Only a reviewer decides (`AGENT_LOOP.md` §6).

| Criterion | Belief | What to check |
|---|---|---|
| EV-01, EV-03 | Mechanism built and adversarially tested offline; **not** verifiable end-to-end without rungs | `tests/test_disposition_invariant.py`, `tests/test_disposition_property.py` |
| PART-01/02/03/05/07 | Enforced structurally; unverified against real threads | `tests/test_envelope_contract.py` |
| ROUTE-01 | Zero-evidence responses cannot be bare | `test_a_zero_evidence_response_must_carry_a_diagnosis` |
| DISC-03 | Depth vocabulary and declared reductions enforced | `tests/test_content_pipeline.py`, `tests/test_envelope_contract.py` |
| DISC-06 | Half: ceiling enforced, degradation absent | `test_an_oversized_response_fails_assembly_rather_than_being_shipped` |
| SEC-01, SEC-03, SEC-04 | Believed met for the code that exists | `tests/test_auth_and_config.py`, `tools/guards` |
| SEC-07 | Code-level only; no capture | `tests/test_egress.py` |
| SEC-08 | No learned anything exists yet; guard in place | `generative_client_sweep` |
| INJ-04 | Hidden constructs removed, counted, sockets denied | `tests/test_content_units.py`, `tests/test_content_pipeline.py` |
| GMAIL-02 | **No.** Synthetic fixtures only; the criterion asks for real mail | — |
| GMAIL-04 | Partial: `scan_scope` conformance enforced, no pager exists | `wire.ScanScopeEntry` |
| GMAIL-06 | **No.** Refresh and expiry paths do not exist | — |
| NFR-01, NFR-04 | Believed met: no keys, clean bootstrap verified | `uv sync --frozen` on a clean copy |
| REG-03, REG-04 | Believed met: no benchmark literals, fixtures synthetic, suite offline | `tests/conftest.py` |
| PROC-01, PROC-03 | Machinery exists; PROC-01/02/06 are adversarial-reviewer criteria and are not mine to claim | `tools/rubric_status.py`, `tests/test_rubric_status.py` |
