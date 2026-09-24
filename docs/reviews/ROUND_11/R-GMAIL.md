# R-GMAIL — Round 11 review: fidelity to the real Gmail API

**Reviewer:** R-GMAIL (fresh instance, per `AGENT_LOOP.md` §3). **Round:** 11. **Date:** 2026-09-01.
**Scope:** the nine guessed response shapes, real-API behaviour handling, preflight-probe
falsifiability, and the fake transport — per the work order and `docs/AGENT_LOOP.md` §4/§7.
This report does not repeat R-SEC's or R-ARCH's domains.

## Execution record

- Wiped `.venv`/`.mypy_cache`/`.pytest_cache`/`.ruff_cache`/`.hypothesis`, `uv sync --all-packages
  --extra dev`. Confirmed `mailweave.__file__` and `mailweave_harness.__file__` resolve under
  `/root/mailweave/{server,harness}/src` (local source, not a stale install).
- `make check`: ruff clean, `ruff format --check` clean, `mypy --strict` 99 files clean, **1,646**
  tests pass, 7 guards clean, rubric `7 PASS / 0 FAIL / 0 BLOCKER / 106 NOT TESTED` — matches
  HANDOFF's claim exactly.
- Targeted re-runs: `pytest tests/test_gmail_client.py tests/test_gmail_models.py
  tests/test_auth_consent.py tests/test_standing_cycle_round11.py tests/test_preflight_probes.py`
  → 107 passed. Spot-checked `test_the_delay_sequence_is_exactly_the_architecture_s`,
  `test_a_response_with_no_scope_field_fails_closed`, `test_a_403_without_a_quota_reason_is_an_
  auth_failure_with_the_reauth_wording` — all present, all pass, assertions match the claims.
- Read in full: `gmail/{client,models,faults,retry,meter,rates}.py`, `auth/consent.py`,
  `tests/fixtures/gmail_shapes.py`, `preflight/{spec,runner}.py`,
  `preflight/probes/{quota,threads,headers,freshness,invisible}.py`.
- **Live documentation, fetched this round** (WebFetch/WebSearch, all 2026-09-01): Gmail API quota
  page, `users.messages.get`/`users.threads.get`/`users.history.list` reference pages, the `Format`
  enum page, `handle-errors` guide, `oauth2/native-app` guide, RFC 6749 §4.2.2, and the **live Gmail
  discovery document** (`gmail:v1`, revision `20260727`) — fetched as JSON and inspected
  programmatically for the `Message`, `Thread`, `ListHistoryResponse`, `ListMessagesResponse`,
  `History`, `Profile` schemas and the `format`/`metadataHeaders`/`historyTypes` parameter
  definitions. A direct `curl` to `gmail.googleapis.com` from this container is blocked by
  organization egress policy; a cached copy of the same discovery document from an earlier session
  in this scratchpad was cross-checked against WebFetch's summary and found consistent (same
  revision, same field text), so it was used as the primary source for schema-level detail.

## Part 1 — the nine guessed shapes

| # | Code assumes | What the documentation says | Agree? |
|---|---|---|---|
| G1 | `format=metadata` on `threads.get` returns per-message `snippet`+`internalDate` | **Confirmed contradiction, verbatim.** Discovery doc: `Format.METADATA` enumDescription = *"Returns only email message ID, labels, and email headers."* — no mention of snippet/internalDate. The `Message`/`Thread` JSON schemas don't vary by format at all (schema has no format-conditional branches), so the guide text is the only source and it doesn't promise either field. **Correctly unresolved; correctly the highest-priority PF-2 question.** |  Genuinely open |
| G2 | `metadataHeaders` honours `References`/`In-Reply-To` | Discovery doc: *"When given and format is METADATA, only include headers specified"* — a **generic allowlist filter**, no special-casing of any header name. This is more settled than the guess implies: the filter mechanism will pass through any requested header that exists on the message. The real open question is whether real mail *has* those headers set, which is a mail-content fact, not an API-shape fact. | Partially resolved — recommend re-labelling PF-2's header half as lower-risk than the snippet/internalDate half |
| G3 | Page tokens fit in 256 single-line ASCII chars | Discovery doc types `nextPageToken` as bare `"type": "string"`, no format, no length, on every listing endpoint. Nothing anywhere bounds it. | Genuinely open — correctly the guess trusted least |
| G4 | Per-user rate limit is 429, or 403 with `{rateLimitExceeded, userRateLimitExceeded, quotaExceeded, dailyLimitExceeded}` | `handle-errors` guide documents exactly `dailyLimitExceeded`/`rateLimitExceeded`/`userRateLimitExceeded` as 403 reasons and states 429 is used for *"mail sending limits and concurrent request limits."* This is **more settled than treated**: official docs favour 403 for general per-user throttling. `quotaExceeded` is not Gmail-specific in the docs found. Both paths are handled regardless, so no functional risk either way. | Largely resolved, in the code's favour |
| G5 | Gmail may send `Retry-After` in seconds form | Not documented for the Gmail API. A third-party write-up citing real operator experience: *"the header is missing... more often than you'd expect."* Code design (raise-never-lower, ignore if absent, fall back to exponential) matches this evidence. | Confirmed unresolved by docs; code's handling is the correct shape for what evidence exists |
| G6 | Error envelope is `error{code, message, errors[{domain,reason,message}], status}` | Google's own `handle-errors` guide's **canonical 403 example carries `errors[]` with no top-level `status` at all.** The HANDOFF text calls `errors[]` "the older spelling" — that framing is backwards for Gmail specifically: `errors[]` is what Gmail's own current guide actually shows; `status` is the one with no confirmed Gmail-specific example. Functionally inert (the code reads `errors[].reason` first and falls back to `status`, so this ordering is already correct), but the *reasoning* in the handoff should be corrected for the next reader. | Code is right; documented reasoning is inverted |
| G7 | `history.list` can repeat a message id within one page | Not documented either direction. | Genuinely open |
| G8 | Installed-app token response carries `scope` | **The load-bearing one — still genuinely unresolved.** Google's native-app guide table lists `scope` among the returned fields *without* the explicit "only returned if..." qualifier it gives `id_token` and `refresh_token_expires_in` — a mild positive signal. But the governing spec (RFC 6749 §4.2.2, cross-checked since §5.1's text wasn't directly quotable) states scope is *"OPTIONAL, if identical to the scope requested by the client; otherwise, REQUIRED"* — and a first consent to a single, unmodified scope (this project's design) is exactly the exact-match case the RFC permits omitting it in. No source found states Google's token endpoint deviates from the RFC here. **This must stay a preflight fact, not an assumption**, and the fail-closed default is correct. The proposed mitigation (`oauth2.googleapis.com/tokeninfo` read-back) is sound: that endpoint's response type (`Tokeninfo`) documents a `scope` field independently of the token endpoint's own behaviour, so it is a genuine second source, not a repeat of the same risk. | Genuinely open, correctly the highest-stakes one |
| G9 | Desktop-app client JSON uses the `installed` key | Standard, uncontested Google Cloud console output. | Settled |

**Verdict on Priority 1:** none of the nine can be closed from documentation alone — that is the
correct outcome for an API that gates real behaviour behind format parameters and quota
mechanics no discovery document states. G1, G3, G7 and G8 remain genuinely open and belong in the
live preflight run exactly as scoped. G4 and G6 are more settled by documentation than the
handoff treats them, in the code's favour both times (no change needed). G2's residual risk is
narrower than stated — it's a mail-content question, not an API-shape one.

## Part 2 — API behaviour: handled / mishandled / silent

| Behaviour | Status | Detail |
|---|---|---|
| `nextPageToken` absent = last page | **Handled** | `more_pages = page.next_page_token is not None` — matches the documented convention exactly, in both `_fetch_list_page` and `_fetch_history`. |
| `historyId` invalidation (expired `startHistoryId`) | **Handled** | `history.list` 404 → `rebaseline_required=True`, matches the discovery doc's own remediation text (*"perform a full sync"*) verbatim. |
| Messages vanishing between `list` and `get` | **Handled** | `get_message`'s 404 is outside `tolerate`, falls to `_classify`'s final branch → `GmailRequestRejected` (`partial_source_failure`), the D.11 code documented for exactly this case. |
| Backoff curve vs. Google's own guidance | **Mishandled** | See finding R-GMAIL-001. Google's guide recommends starting at ≥1s; this client's whole retry budget is 1.5s. |
| Partial failures within a batch | **Silent** | No batcher exists this round (disclosed). Nothing to mishandle yet. |
| Threads growing between calls | **Silent** | No cross-call staleness check exists or is claimed; each `threads.get` is self-consistent at the instant it runs. Out of this round's scope (ranking/escalation not built). |
| `format` interactions with scope (`FULL`/`RAW` blocked under `gmail.metadata`) | **N/A, correctly** | `SERVER_SCOPES` is `gmail.readonly`, not `gmail.metadata`, so the discovery doc's format/scope restriction never applies. |
| `labelIds` structured filter (`messages.list`) | **Silent** | Real, documented, repeated `labelIds` query param exists; the client only exposes free-text `q`. Reasonable (Gmail's `label:` search operator is equivalent) but unexercised — no test constructs a `labelIds`-only query. |
| 403 `domainPolicy` remediation text | **Mishandled** (message only) | See finding R-GMAIL-003. |
| Retry-attempt quota accounting | **Assumption, undisclosed as such** | `meter.py`'s "every attempt is charged, including the one that 429'd" is stated as settled fact; no Google source confirms a refused (over-quota) request is itself billed. Should be added to the guess list, or explicitly caveated the way `quota_units` already is. |

## Part 3 — can the probes falsify anything?

All six probes were read for their `analyse` half and exercised via `test_preflight_probes.py`
(35 tests, all pass, including both PASS- and FAIL-triggering observations per probe).

- **PF-1 / PF-thread-size-ceiling / PF-2 / PF-cf-strip-damage / PF-freshness-raw**: genuinely
  falsifiable. Each has a real "this observation fails the probe" input distinct from the passing
  one, each states its bias direction explicitly (PF-1 and PF-thread-size-ceiling can only produce
  false PASSes from an incomplete sample, never false FAILs — the safe direction), and each
  correctly reports `INCONCLUSIVE` rather than PASS when the sample can't speak to the question
  (no Arabic mail, no shared threads, no arrivals in the window). None is constructed to confirm
  whatever it sees.
- **PF-3-quota-units — the implementer's own flagged weak point, confirmed weak, in a way not yet
  fully disclosed.** The rank-order falsifier is a good primary defense: it is genuinely
  order-sensitive and survives the stated assumptions (one bucket/project/window) being
  approximately rather than exactly true. But `measure_endpoint`'s `calls_completed` counts
  **successful logical calls**, not HTTP attempts — a call that transparently retries once on a
  transient 5xx before succeeding is still counted as `1`. Since `inferred_units = budget /
  calls_completed`, any hidden retries during the drive-to-refusal loop bias the inferred cost
  **upward** (fewer completed calls than actual attempts spent from the same budget). This is a
  second, undisclosed assumption beyond the three the spec names, though it is directionally safe:
  an inflated inferred cost is more likely to trip the agreement-factor FAIL and trigger the
  conservative halving than to hide a real overcost. **Recommend: report PF-3 explicitly as an
  inference layered on an inference — cost-from-refusal, and completed-calls-as-a-proxy-for-
  attempts-spent — not as a measurement**, exactly as the work order's Priority 3 asked. The
  probe's own `--plan` output and findings dict already carry `calibration_before_this_run` and
  the assumptions note; add this one to it before the live run.

## Part 4 — the fake transport

`tests/fixtures/gmail_shapes.py` does not encode the same assumptions the client makes. It sits
**behind** `net.egress.build_client`'s allowlist transport (verified: `build_client(inner=fake.
transport())` in `test_gmail_client.py`, not a stub of `GmailClient` methods), so URL
construction, the bearer header, the repeated `metadataHeaders` key and the retry ladder are all
still exercised against something that looks like an HTTP boundary. Every fixture carries an
explicit `[DISCOVERY]` or `[PREFLIGHT PF-n]` provenance marker, and cross-checking a sample against
the live discovery document found no mismatch: `MESSAGES_LIST_PAGE_1`/`MESSAGE_FULL`/`PROFILE`
match the real schemas field-for-field, `THREAD_METADATA_NO_INTERNAL_DATE` is honestly labelled as
the pessimistic G1 branch rather than asserted, and the duplicate-id `HISTORY_PAGE` fixture is
labelled `[PREFLIGHT]` rather than presented as fact. `issue #239`, cited by `PF-1`'s falsifier and
by `threads.py`'s docstring as "100 rows, listing 137," is a real, findable GitHub issue (Gmail
thread-truncation report), not a fabricated citation. **Where the transport and the client agree,
it is because both cite the same external document, not because one was built from the other** —
the marker discipline is what makes that checkable rather than asserted. This is worth trusting
more than the average fixture suite, precisely because of the discipline the labels impose.

## Findings

```
ID:            R-GMAIL-001
Severity:      MEDIUM
Rubric:        GMAIL-05 (quota and rate-limit behaviour) — contributes to, not yet gate-blocking
Location:      server/src/mailweave/constants.py:113-117 (RETRY_BASE_MS=250, MAX_RETRIES=3,
               MAX_BACKOFF_TOTAL_MS=1500); server/src/mailweave/gmail/retry.py next_delay_ms
Reproduction:  Google's handle-errors guide: "you might retry a failed request after one
               second, then after two seconds, and then after four seconds... start retry
               periods at least one second after the error." Compare BackoffPolicy defaults.
Expected:      A retry curve that gives a real per-minute rate-limit window a chance to clear,
               per Google's own stated guidance (>=1s initial wait).
Actual:        Base delay 250ms, whole retry budget capped at 1500ms wall-clock, at most 2
               retries reachable (HANDOFF's own point 3). Every genuine per-user rate limit
               will still be in effect when the client gives up, so GmailRateLimited is close
               to guaranteed on first contact with a real limit rather than something the
               backoff sometimes works around.
Required fix:  Not a Round 11 code fix — AD A.5a owns these figures. Escalate per AGENT_LOOP
               §8 ("a real Gmail behavior contradicts a load-bearing assumption in
               ARCHITECTURE_DECISION.md") for the human/orchestrator to reconcile against
               Google's documented guidance, informed by PF-3's live rank-order measurement.
```

```
ID:            R-GMAIL-002
Severity:      MEDIUM
Rubric:        none — out-of-rubric defect (probe-methodology precision, feeds GMAIL-05)
Location:      harness/src/mailweave_harness/preflight/probes/quota.py:80-115
               (measure_endpoint), 118-126 (inferred_units)
Reproduction:  Read measure_endpoint: `completed += 1` fires once per successful make_call(),
               and _request retries transparently inside one logical call.
Expected:      inferred_units_per_call should be budget-per-attempt-spent, since that is what a
               token bucket actually charges against.
Actual:        It is budget-per-successful-logical-call. Any transient-5xx retry inside a
               "completed" call inflates the apparent per-call cost.
Required fix:  Either have GmailClient/CallMeter expose attempts-in-this-run to the probe, or
               state this as a second explicit assumption in PF-3's ProbeSpec (validates/
               pre_registered_rules) and findings dict, alongside the three already named.
```

```
ID:            R-GMAIL-003
Severity:      LOW
Rubric:        GMAIL-06 (auth lifecycle exercised)
Location:      server/src/mailweave/gmail/client.py:393-402 (GmailAuthExpired branch)
Reproduction:  tests/test_gmail_client.py::test_a_403_without_a_quota_reason_is_an_auth_
               failure_with_the_reauth_wording covers `insufficientPermissions`; no test
               covers `domainPolicy`.
Expected:      Remediation text should not tell an owner to re-consent for a failure Google's
               own guide says "requires domain administrator approval."
Actual:        Every non-rate-limit 403 gets the identical "run `mailweave auth login`"
               message regardless of reason.
Required fix:  Branch the message (or at minimum the logged reason) so a domainPolicy 403
               names the real remedy; add a test fixture for it.
```

```
ID:            R-GMAIL-004
Severity:      LOW
Rubric:        none — out-of-rubric defect (docstring accuracy)
Location:      server/src/mailweave/gmail/models.py:152-156 (HistoryMessageAdded)
Reproduction:  Read the class: field is `message: MessageRef`; MessageRef (line 87-97) has
               only `id`/`thread_id`.
Expected:      Docstring says "Its `message` carries id / threadId / labelIds."
Actual:        labelIds is not modelled; extra="ignore" silently drops it if Gmail sends it.
Required fix:  Correct the docstring, or add label_ids to MessageRef if a future rung needs it
               — either is fine, but the two must agree.
```

## Per-criterion recommendations

All seven `GMAIL-0X` criteria remain, correctly, `NOT TESTED` — none can move without a live
mailbox, and HANDOFF did not attempt to mark any, matching AGENT_LOOP §6. No regression found in
the 7 criteria already `PASS`. R-GMAIL's own domain check (client correctness against documented
Gmail behaviour, and probe falsifiability) finds:

- **Zero BLOCKER, zero HIGH.** Nothing here blocks Round 11's gate on its own.
- **Two MEDIUM** (R-GMAIL-001, -002) — both are pre-existing-assumption or probe-methodology gaps
  that the live preflight run is positioned to catch or correct, not code defects introduced this
  round. Recommend they travel with the live run as named watch items rather than block it.
- **Two LOW** (R-GMAIL-003, -004) — schedulable to a later round per AGENT_LOOP §4's MEDIUM/LOW
  disposition; neither changes behaviour an owner would notice before the fix lands.
- **G8 (scope field)** is the one item in this review with first-run-breaking potential; the
  fail-closed design is correct and should not be relaxed. Recommend implementing the
  `tokeninfo` fallback (already scoped by the implementer) before or alongside the owner's first
  `auth login`, not deferred as a nice-to-have.

**Recommendation: Round 11 is not blocked by R-GMAIL's domain.** The client's documented-shape
assumptions are honestly labelled and, where checkable against live Google documentation this
round, mostly hold or are more favourable than treated. The four findings above are real and
should be tracked, but none rises to a level that should stop the round on its own.
