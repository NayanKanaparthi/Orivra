# Run 1 — raw evidence preserved, automatic verdict INVALID

`deadline-validation-run1-raw.json` is unmodified. Its measurements stand. **Its
`adoptable: true` does not**, and nothing may cite it.

## Why the verdict is void

The run compared 7,700 ms against 12,300 ms on queries whose largest made **four Gmail
requests** and whose longest took **1,721 ms**. A wall-clock deadline governs how many
sequential calls a query may make; at four requests neither deadline was approached, so the
two were never distinguished. The rule counted a query as "informative" when both arms
answered, which is not the same as when the clock was exercised. A comparison that cannot
fail decides nothing.

Same shape as two defects this project has already shipped and fixed: R-MCP-030's certifying
matrix that held source count at one, and round 26's `if result.is_error: continue`. A check
that passes without exercising what it is about.

## What run 1 still establishes, and it is worth keeping

* `delimiter`: identical evidence, endpoint counts and rendered size under both deadlines
  (`1a075a3220ea9ae8` at `body_clean`, 4 HTTP, 17,774 chars). The candidate is not *worse*
  than the bound on a narrow search.
* **The narrowest search this mailbox can produce took 1,721 ms against a shipped deadline of
  2,000 ms.** One match, one thread, four requests, within 280 ms of the published figure.
  That corroborates PF-21's failure from an independent direction and is the more useful
  result of the two.
* `has:attachment` answered with no evidence in 2,103 characters, correctly and without caps.
* `after:2026/09/01` was refused under both arms. Run 1 attributed that to R-MCP-033's width
  limit. **That was a guess**, and run 2's rule records what a refusal said rather than
  deciding what caused it.

## What replaces it

Run 2: three arms including the shipped 2,000 ms baseline, counterbalanced running order over
repeats, `search_wall_ms` kept apart from `expansion_wall_ms`, non-empty evidence required
before a query counts as informative, asymmetric declines blocking, refusal details captured,
and a registered condition that the baseline must visibly differ before any conclusion is
drawn about which larger value to take.
