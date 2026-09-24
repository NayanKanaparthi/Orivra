# ROUND 03 — Consolidated findings and gate decision

**Orchestrator, 2026-08-31.** Reviewers: R-SEC, R-RETR (both independent, neither wrote the code).

## Gate decision: **ROUND 03 DOES NOT CLOSE**

Three HIGH findings open. But this round moved the project further than the count suggests:
the central evidence-preservation work is now closed, and what remains is adjacent.

| Finding | Verdict |
|---|---|
| H1b shortlist sealed | **CLOSED** — both Round-2 probes now raise; 9 fresh attacks (mixed real/fake ids, ordering, k=0/negative/huge, empty pages, cross-clause dupes, page reuse, subclass override, double shortlist) all held. `_admit` verified as the sole writer of `H` by reading the AST test, not just running it |
| H2b dishonest map reconstruction | **CLOSED** — the 37-id / 5-of-42 rebuild now raises at `record_shortlist` before any `Source` is built |
| R-RETR-001 collapsed-run dedup | **CLOSED** at id level |
| H4, M2, M3 (Round 2) | **CLOSED**, independently reverified |
| R-SEC-008/009/010 | **PARTIALLY CLOSED** — demonstrated shapes fixed, same-shaped gaps remain |

## Open HIGH

| ID | Defect | Fix |
|----|--------|-----|
| **R-RETR-002** | `_counts_match_the_payload` compares collapsed runs by member id but never by `positions`. Two runs with disjoint ids claiming the same thread slot build cleanly through a full `map_id`-bearing envelope. The fix's own rationale states "one position, one disposition" and that property is unchecked at the position level | Check position occupancy, not just id membership |
| **R-RETR-004** | The `H-sem ⊆ H-lex ∪ H-hist` narrowing conflicts with ARCHITECTURE_DECISION §D.5. Pool construction's first-choice source arrives via `threads.get`, not `messages.list`/`history.list`, so when WS-08 lands the seal will reject a legitimate top-k selection | Architecture amendment **A2** below |
| **R-SEC-013** | 7 of 9 further constant-obfuscation idioms defeat all four content-matching guards with zero violations: `bytes.fromhex().decode()`, `"".join()`, `%`-formatting, `.format()`, `str.translate()`, reversed slicing, `int.to_bytes()` | Fold or honestly document each |

## Open MEDIUM

- **R-SEC-014** class-attribute dispatch bypasses the disk-write guard.
- **R-SEC-015** the scope-blind alias index produces **false positives on ordinary code**: two unrelated functions reusing a local name cause an innocent `str.format` call to be flagged. A guard that fires on innocent code gets disabled by the next engineer, which is its own failure mode.
- **R-SEC-016** the open-position fix is a 5-module allowlist rather than structural; `tarfile.open`, `shelve.open` and `zipfile.ZipFile` reproduce the original bug.

## The architectural result of this round

R-RETR independently reproduced the implementer's own disclosure that `FetchedIds` is an
ordinary public constructor, then went further and defeated the capability token itself by
subclassing and overriding `_release`.

Their verdict, which I accept: **no in-process construction can close this.** Not
fetcher-only minting, not binding a page to observed response bytes. A verifier living in the
same interpreter as the party it checks is not a boundary. This is not a defect to fix; it is
where the in-process guarantee ends.

Consequence, and it is significant: **EV-01 splits.** "Bounded below" — every id the ledger
knows about is accounted for — is provable in-process and is essentially done. "Bounded above"
— the ledger knows about every id Gmail actually returned — cannot pass in-process at all.
It requires the counting proxy, and the proxy as specified today is not sufficient to deliver
it. See amendment A1.

## Criteria promoted this round

`SEC-04` and `INJ-04` (bidi/zero-width scope), both on R-SEC evidence. Recorded in
`RUBRIC_TRANSITIONS.md` with reproduction, along with seven from Round 1 that the orchestrator
owed. 9 of 113 now PASS.

Deliberately not promoted: the OD-2 outcome-enforcement probes from `R-ORCH.md`. `R-ORCH` is
not an AGENT_LOOP §2.3 reviewer domain, and recording orchestrator probes as PASS is the
self-certification §1 forbids. Those wait for a domain reviewer.
