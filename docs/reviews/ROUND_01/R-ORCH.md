# ROUND 01 — Orchestrator verification (R-ORCH)

**Reviewer:** orchestrator, 2026-08-31. Did not write the code (an implementer agent did),
so this does not violate `AGENT_LOOP.md` §1. Run because four parallel reviewer agents were
cut off by a session rate limit; independent reviewers still cover R-DISC, R-SEC and R-ARCH.

**Method:** adversarial probes executed against the built package, not inspection of
`HANDOFF.md` claims. Probe sources: `/tmp/probe/attack.py`, `/tmp/probe/od2b.py`.

---

## Findings

### R-ORCH-001 · HIGH · Evidence preservation passes vacuously when `H` is under-recorded

- **Rubric:** EV-01, I-1
- **Location:** `server/src/mailweave/envelope/disposition.py`, `DispositionLedger.certify`
- **Reproduction:** probe E. A caller simulating `messages.list` returning 100 IDs records
  only the first 10 via `record_list_page`, then discloses those 10.
- **Expected:** the invariant should not be satisfiable while 90 retrieved messages are
  unaccounted for.
- **Actual:** `certify` returns a valid certificate — `H=10`, `withheld=0`, no error. The 90
  IDs are invisible to every check, because `H` is defined by what was *recorded*, not by
  what was *fetched*.
- **Assessment:** the set-difference machinery is correct and I could not defeat it on any
  path where `H` is complete (probes C, F, G all blocked). The entire guarantee therefore
  rests on `H` being complete, and nothing currently enforces that. This is precisely the
  Gmail `search_threads` failure mode that MailWeave exists to fix, relocated from the
  response builder to the ledger's input. The implementer identified this themselves in
  `HANDOFF.md` §6, which is to their credit; confirming it does not reduce its severity.
- **Required fix:** WS-02's Gmail client must be structurally unable to return a list
  result without recording it into a ledger — the transport, not the caller, owns the
  recording. This must land before any retrieval rung ships, not after. Round 2 work order
  to carry it as a gating item.

### R-ORCH-002 · LOW · Mint token reachable via private name (acknowledged, not a defect)

- **Location:** `disposition.py`, `_MINT_TOKEN`
- **Reproduction:** probe B forges a certificate by importing the private name.
- **Assessment:** the module docstring states plainly that this "is not a defence against
  code that deliberately reaches for a private name in the same process, and is not claimed
  to be." The claim matches the behavior, which is what claim discipline requires. Recorded
  for completeness; no action. A reviewer-facing note only.

---

## Verified working (evidence for criterion recommendations)

| Probe | Result |
|-------|--------|
| A · forge certificate with a fake token | **blocked** — `DispositionInvariantError` |
| C · certify while silently dropping a hit | **blocked** — names the exact unaccounted ID |
| F · shortlist exceeding declared `k` | **blocked** — `|H|` cannot be shrunk at review time |
| G · lift a certificate onto a different disclosed set | **blocked** — digest binds to payload |
| OD-2 · `not_found` + `not_tried[why=budget]` | **blocked** |
| OD-2 · `not_found` + `why=cap` / `timeout` / `error` | **blocked** (all three) |
| OD-2 · `not_found` + non-empty `budget_caps_hit` | **blocked** |
| OD-2 · `not_found`, nothing skipped, no caps | **allowed** (correct) |
| OD-2 · `not_found` + `why=not_applicable` | **allowed** (correct) |

Also confirmed by inspection of the live vocabularies:

- `Outcome` is exactly `{answered, not_found, inconclusive}` — OD-2's three-way distinction
  exists in the type system, not only in prose.
- `NotTriedWhy` is closed to `{not_applicable, budget, cap, timeout, error}`, which is what
  makes the OD-2 rule machine-checkable rather than a matter of judgment.
- A `not_tried` entry with a *blocking* reason is rejected unless it carries an
  `Affordance`, so a skipped rung must come with the call that would reach it.
- `Role` carries all seven values; `Depth` is a closed five-value set.
- `Completeness` has exactly one member, `AS_REPORTED_BY_SOURCE`. There is no value in the
  type system for asserting absolute completeness, which is the strongest possible form of
  PART-01's honesty requirement: the dishonest claim is not merely discouraged, it is
  unrepresentable.

---

## Criterion recommendations

| Criterion | Recommendation | Evidence |
|-----------|----------------|----------|
| OD-2 outcome enforcement (EV-04 / AD-03 / ROUTE-01 as they bind `outcome`) | **PASS** | nine probes above; all five violation shapes rejected, both legitimate shapes allowed |
| PART-01 truthful totals (type-level portion) | **PASS** | `Completeness` admits no absolute-completeness value |
| EV-01 / I-1 evidence preservation | **NOT YET** — blocked by R-ORCH-001 | machinery correct, input completeness unenforced |

Criteria in the R-DISC, R-SEC and R-ARCH domains are not assessed here and remain
`NOT TESTED` pending those reviews.
