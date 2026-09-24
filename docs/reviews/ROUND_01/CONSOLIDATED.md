# ROUND 01 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-ORCH (orchestrator probes), R-SEC, R-ARCH, R-DISC.
R-RETR's domain was covered by R-ORCH after four parallel Opus reviewers were cut off by a
session rate limit; the remaining three ran on a lighter model and completed.

## Gate decision: **ROUND 01 DOES NOT CLOSE**

`AGENT_LOOP.md` §5 step 6 requires zero open BLOCKER and zero open HIGH.

| Severity | Count |
|----------|-------|
| BLOCKER | 0 |
| HIGH | 6 |
| MEDIUM | 9 |
| LOW | 9 |

Round 2 is a fix round over the HIGH findings and the three MEDIUMs that share their root
cause. No rubric criterion is promoted to PASS except the four listed at the bottom.

---

## The pattern worth naming

Three reviewers, working independently on different layers, found the same defect shape:

- **R-ORCH-001** — the disposition ledger's `H` is what a caller *recorded*, not what Gmail
  *returned*. Record 10 of 100 fetched IDs and the evidence-preservation invariant passes
  with 90 messages invisible.
- **R-DISC-001** — a `Source` carrying `map_id`, which claims to be a full thread map, can
  omit 88% of the thread's messages with no stub row, no collapsed run and no withheld
  record. Construction succeeds.
- **R-ARCH (MEDIUM)** — the content pipeline asserts that *some* reduction was declared, not
  that the declared magnitude matches actual shrinkage. A stripper removing 220 of 245
  characters while declaring 1 passes.

This is one bug wearing three costumes: **wherever the system states what it represents, and
separately computes what it actually enumerated, the two can silently diverge.** It is the
exact shape of Gmail issue #296 — the thing MailWeave exists to fix — reappearing inside
MailWeave at every layer where that gap is allowed to exist.

The Round 1 design closed this gap in one place (`withheld := H − disclosed`, which resisted
every attack that assumed a complete `H`). The correct response is to apply the same
inversion at the other three sites rather than to patch each symptom: **the claim must be
derived from the enumeration, never asserted alongside it.**

---

## HIGH findings (all must close before Round 1 gates)

| ID | Source | Defect | Required fix |
|----|--------|--------|--------------|
| **H1** | R-ORCH-001, confirmed R-ARCH | `H` is caller-recorded, so evidence preservation passes vacuously when a rung under-records | The transport owns recording. `list_messages(ledger, ...) -> ScanScopeEntry`, never a bare ID list. Gates WS-02 |
| **H2** | R-DISC-001 | `map_id` claims a full map while omitting messages with no accounting | Derive map completeness from enumeration: a claimed map must account for every message as row, collapsed run, or withheld record |
| **H3** | R-SEC-001 | All six AST guards bypassable with ordinary code (string concat, `importlib.import_module`, `Path.open("w")`). A file violating all six intents passes with zero violations | Either harden materially, or narrow each guard's documented claim to what it actually catches. An overstated guard is worse than none, because the rubric leans on it |
| **H4** | R-SEC-002 | HTML→text is quadratic in DOM nesting; ~1MB crafted body reaches minutes of hang. lxml fallback silently drops all content at extreme depth | Depth and size caps before parse, with any truncation declared as a `Reduction`. No silent drops |
| **H5** | R-ARCH | Quote stripper mislabels Outlook/forwarded blocks as `signature` rather than `quoted`, and fails entirely on signatures lacking a `--` delimiter, leaking them into `body_clean` | Fix classification and the no-delimiter case; token economics depend on this |
| **H6** | R-DISC-002 (MEDIUM, promoted) | `mark_self_truncated()` bypasses the size ceiling with zero verified shrinkage — demonstrated shipping 27,000 tokens against a 9,000-token ceiling | Verify actual shrinkage; a truncation claim must be derived from measured size |

H6 is promoted from MEDIUM because it is the same derive-don't-assert defect as H1/H2 and
should be fixed in the same pass.

## MEDIUM sharing the root cause (fix in Round 2)

- R-ARCH: declared reduction magnitude unverified against actual shrinkage.
- R-SEC-003: `TokenStore.save()` is not atomic; a crash between write and `chmod` can leave a
  refresh token at 0644. Reproduced.
- R-SEC-005: unicode bidi-override characters pass through the pipeline unflagged.

## Remaining MEDIUM/LOW

Carried in `FINDINGS_LEDGER.md`, scheduled but not round-blocking: non-English "wrote:" lines
leaking; `fetched_at` accepting any non-empty string; `constraint_coverage` dead placeholder;
`check_url()` raising `idna` errors instead of `EgressBlocked` (fails closed, wrong type); no
guard against future code bypassing egress via raw `httpx.Client()`; `ruff format --check`
failing on a reviewer's own markdown; 8 of 10 `Reason.render()` variants and the OD-3
parent/child-stub shape untested; wire field order burying the partiality signal behind bulk
content; payload-size and deep-nesting robustness gaps.

---

## What held up

Worth recording, because these were attacked and did not break:

- The `withheld := H − disclosed` set difference resisted every probe assuming a complete
  `H`: forged certificates, silent drops, oversized shortlists, and lifting a certificate
  onto a different disclosed payload.
- OD-2 is enforced in the type system. All five violation shapes rejected; both legitimate
  shapes allowed. `Outcome` is exactly the three decided values, `NotTriedWhy` is closed, and
  a blocking `not_tried` entry cannot exist without a recovery affordance.
- `Completeness` admits exactly one value, `AS_REPORTED_BY_SOURCE`. There is no way to assert
  absolute completeness in the type system, which is the strongest available form of PART-01.
- 7 of 10 response obligations are ENFORCED (types reject violations), 3 EXPRESSIBLE, 0 ABSENT.
- Egress held against userinfo authorities, suffix and prefix spoofing, IP literals, redirects
  and unicode confusables.
- Clean build reproduced independently from the lockfile: 199/199 tests, lint, types, guards.

## Criteria promoted to PASS this round

| Criterion | Reviewer | Evidence |
|-----------|----------|----------|
| OD-2 outcome enforcement (as bound by EV-04 / AD-03 / ROUTE-01) | R-ORCH | nine probes; all violations rejected, legitimate shapes allowed |
| PART-02, PART-03, PART-07 (structural half) | R-DISC | 25 adversarial construction probes |
| NFR-01, NFR-04, REG-04 | R-SEC | execution record |
| Reproducibility of the clean build | R-ARCH | `uv sync --frozen` + full suite in a fresh copy |

Everything else remains `NOT TESTED` or `FAIL`, per `RUBRIC_TRANSITIONS.md`.
